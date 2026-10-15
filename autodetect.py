import json
import copy
from collections import OrderedDict
import ntpath
import re
import time
from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path
import requests
from core import Rule
from normalization import normalized_name, search_name, edition_conflict
from automation import game_key

DISCORD_DETECTABLE_URL = 'https://discord.com/api/v10/applications/detectable'
GENERIC_EXECUTABLES = {
    'steam.exe', 'epicgameslauncher.exe', 'epicgameslauncherhelper.exe',
    'battle.net.exe', 'upc.exe', 'uplay.exe', 'origin.exe',
    'eadesktop.exe', 'riotclientservices.exe', 'launcher.exe',
    'launchpad.exe', 'patcher.exe', 'updater.exe', 'start.exe',
    'unitycrashhandler64.exe', 'unitycrashhandler32.exe', 'crashpad_handler.exe',
    'werfault.exe', 'applicationframehost.exe', 'runtimebroker.exe',
    'shellexperiencehost.exe', 'startmenuexperiencehost.exe', 'searchhost.exe',
    'textinputhost.exe', 'dllhost.exe', 'conhost.exe', 'explorer.exe',
    'taskhostw.exe', 'ctfmon.exe', 'audiodg.exe', 'dwm.exe',
    'easyanticheat.exe', 'easyanticheat_eos.exe', 'easyanticheat_eos_setup.exe',
    'start_protected_game.exe', 'eac_launcher.exe', 'eac.exe',
    # Common development/build/shell executables. Discord's public detectable list can
    # contain overly-generic executable names from individual titles, so these must
    # never be presented as games even if a remote record happens to match them.
    'cl.exe', 'link.exe', 'lib.exe', 'rc.exe', 'mt.exe', 'csc.exe', 'vbc.exe',
    'msbuild.exe', 'devenv.exe', 'cmake.exe', 'ninja.exe', 'make.exe',
    'python.exe', 'pythonw.exe', 'py.exe', 'node.exe', 'npm.exe', 'npx.exe',
    'java.exe', 'javaw.exe', 'game.exe',
    'cmd.exe', 'powershell.exe', 'pwsh.exe', 'git.exe', 'git-bash.exe', 'dotnet.exe',
    # Generic installer / maintenance executables. These names are frequently reused
    # by completely unrelated software and must never become automatic game rules.
    'setup.exe', 'setup32.exe', 'setup64.exe', 'install.exe', 'installer.exe',
    'uninstall.exe', 'uninstaller.exe', 'unins000.exe', 'update.exe', 'patch.exe',
    'maintenance.exe', 'bootstrapper.exe',
    # PUBG helper/test processes. Only the actual game process TslGame.exe is
    # treated as PUBG for automatic detection.
    'tslgame_be.exe', 'execpubg.exe',
}
BLOCKED_EXECUTABLE_PARTS = (
    'launcher', 'launch', 'updater', 'patcher', 'bootstrap',
    'gamecenter', 'gamelauncher', 'clientloader',
    'crashhandler', 'crashpad', 'crashreport', 'errorreport',
    'applicationframehost', 'runtimebroker', 'shellexperiencehost',
    'startmenuexperiencehost', 'textinputhost',
    'easyanticheat', 'anticheat', 'eaclauncher', 'protectedgame',
)

# Only match names that are themselves generic installer/maintenance binaries.
# Do not use a loose substring test here because a legitimate game executable could
# contain words such as "install" as part of a longer product-specific name.
GENERIC_INSTALLER_STEMS = re.compile(
    r'^(?:setup|install|installer|uninstall|uninstaller|update|updater|patch|patcher|'
    r'unins\d*|maintenance|bootstrapper)(?:x86|x64|32|64)?$',
    re.IGNORECASE,
)

DROP_WORDS = {
    'game', 'online', 'launcher', 'client', 'demo', 'beta', 'alpha',
    'edition', 'definitive', 'ultimate', 'complete', 'remastered',
    'reboot', 'test', 'public', 'release', 'early', 'access', 'steam',
}

# Some CHZZK game categories are localized and are best searched by their Korean
# display name.  Automatic detection may override the Discord/EXE English name
# for these known cases.  Values here are the only search keywords used for the
# matching process, which avoids an unnecessary English CHZZK query.
LOCALIZED_SEARCH_OVERRIDES = {
    'vrchat.exe': ('VR챗',),
    'ride-win64-shipping.exe': ('RV 데어 옛?',),
    'mimesis.exe': ('미메시스',),
    'smilemo.exe': ('스마일모',),
}

# Discord lists Pratfall (1468444820484784333) without any executables.
# Steam app_info 4244510 lists Pratfall.exe as the public Windows game binary.
# Keep confirmed exceptions separate from name-based heuristics and helper binaries.
VERIFIED_EXECUTABLE_COMPATIBILITY = {
    'pratfall.exe': {'id': '1468444820484784333', 'name': 'Pratfall',
                     'aliases': ['프랫폴']},
}


def with_verified_executable_compatibility(entries):
    result = dict(entries)
    for executable, verified in VERIFIED_EXECUTABLE_COMPATIBILITY.items():
        records = list(result.get(executable, []))
        match = next((i for i, row in enumerate(records)
                      if row.get('id') == verified['id']
                      or (not row.get('id') and str(row.get('name', '')).casefold() == verified['name'].casefold())), None)
        if match is None:
            records.append(copy.deepcopy(verified))
        else:
            record = dict(records[match])
            record['id'] = verified['id']
            record['aliases'] = list(dict.fromkeys([*record.get('aliases', []), *verified['aliases']]))[:8]
            records[match] = record
        result[executable] = records
    return result


# One LoL signal per scan: match first, otherwise the lobby client.
LEAGUE_EXECUTABLES = ('league of legends.exe', 'leagueclient.exe')
LEAGUE_CLIENT_EXECUTABLES = ('leagueclientux.exe', 'leagueclientuxrender.exe')
GENERIC_EXECUTABLES.update(LEAGUE_CLIENT_EXECUTABLES)
LEAGUE_NAMES = ('League of Legends', '리그 오브 레전드', 'LoL')
for _league_exe in LEAGUE_EXECUTABLES:
    LOCALIZED_SEARCH_OVERRIDES[_league_exe] = ('리그 오브 레전드',)


def with_game_client_compatibility(entries):
    result = {}
    for key, records in entries.items():
        if is_ignored_process(key):
            continue
        kept = [record for record in records
                if str(record.get('name') or '').casefold() != 'league of legends'
                or key.casefold() in LEAGUE_EXECUTABLES]
        if kept:
            result[key] = kept
    for executable in LEAGUE_EXECUTABLES:
        records = result.setdefault(executable, [])
        matching = [i for i, item in enumerate(records)
                    if str(item.get('name') or '').casefold() == 'league of legends']
        if matching:
            i = matching[0]
            record = dict(records[i])
            record['aliases'] = list(dict.fromkeys([*LEAGUE_NAMES[1:], *record.get('aliases', [])]))[:8]
            records[i] = record
        else:
            records.append({'name': LEAGUE_NAMES[0], 'aliases': list(LEAGUE_NAMES[1:]), '_source': 'compatibility', 'discord_name': ''})
    return result


def game_process_details(processes, entries):
    result = {}
    for process in processes:
        records = entries.get(process_basename(process).casefold(), [])
        if len(records) != 1:
            continue
        record = records[0]
        name = str(record.get('name') or '').strip()
        preferred = LOCALIZED_SEARCH_OVERRIDES.get(process_basename(process).casefold(), ())
        result[process.casefold()] = {'name': name, 'keyword': preferred[0] if preferred else name}
    return result


def normalize_name(value):
    return normalized_name(value)


def contains_hangul(value):
    return bool(re.search(r'[\uac00-\ud7a3\u3131-\u318e]', value or ''))


def exact_category_identity(category, names):
    targets = {normalize_name(name) for name in names if normalize_name(name)}
    return bool(targets & {
        normalize_name(str(category.get('categoryId') or '')),
        normalize_name(str(category.get('categoryValue') or '')),
    })


def league_rule_processes(rule):
    category = {'categoryId': rule.category_id, 'categoryValue': rule.category_name}
    if (normalize_name(rule.game_name) == normalize_name(LEAGUE_NAMES[0])
            and any(p.casefold() in (*LEAGUE_EXECUTABLES, *LEAGUE_CLIENT_EXECUTABLES)
                    for p in rule.processes)
            and exact_category_identity(category, LEAGUE_NAMES)):
        return ('League of Legends.exe', 'LeagueClient.exe')
    return rule.processes


def category_choice_process_key(process):
    key = process_basename(process).casefold()
    return 'league-of-legends' if key in LEAGUE_EXECUTABLES else key


def tokenize(value):
    return [v for v in re.findall(r'[a-z0-9]+|[\uac00-\ud7a3]+', (value or '').casefold()) if len(v) > 1]


def normalize_keyword(value):
    return search_name(value)


def build_search_keywords(game_name, aliases, process_name=''):
    process = process_basename(process_name)
    override = LOCALIZED_SEARCH_OVERRIDES.get(process.casefold())
    if override:
        return [str(value).strip() for value in override if str(value).strip()][:12]

    values = [str(game_name or '').strip()]
    values.extend(str(a).strip() for a in aliases if str(a).strip())
    stem = process
    if stem.casefold().endswith('.exe'):
        stem = stem[:-4]
    if stem:
        values.append(stem)

    keywords = []
    for value in values:
        if not value:
            continue
        for candidate in (value, normalize_keyword(value)):
            item = candidate.strip()
            if not item:
                continue
            if item not in keywords:
                keywords.append(item)

    # Korean keywords first because CHZZK category search tends to match localized names better.
    keywords.sort(key=lambda item: (0 if contains_hangul(item) else 1, len(item), item.casefold()))
    return keywords[:12]


def process_basename(value):
    return ntpath.basename(value or '').strip()


def sanitize_executable(value):
    raw = str(value or '').strip().replace('\\', '/')
    if raw.startswith('>') or any(char in raw for char in '*?'):
        return ''
    name = ntpath.basename(raw).strip()
    if not name or not name.casefold().endswith('.exe'):
        return ''
    return name


def is_launcher_executable(value):
    name = sanitize_executable(value)
    if not name:
        return True
    key = name.casefold()
    if key in GENERIC_EXECUTABLES:
        return True
    stem = key[:-4] if key.endswith('.exe') else key
    compact = re.sub(r'[^a-z0-9]+', '', stem)
    if GENERIC_INSTALLER_STEMS.fullmatch(compact):
        return True
    return any(part in compact for part in BLOCKED_EXECUTABLE_PARTS)

def is_ignored_process(value):
    """Return True for launchers, crash reporters and common Windows shell helpers."""
    return is_launcher_executable(value)


def detectable_running_processes(processes, entries):
    """Return running executable names that Discord identifies as games.

    ``processes`` is the conservative OS process-name snapshot. ``entries`` is the
    Discord detectable executable index.  Matching is case-insensitive and no process
    handles, paths, modules, or memory are inspected.
    """
    active = {}
    for value in processes if isinstance(processes, (list, tuple, set)) else []:
        name = process_basename(value)
        if not name or is_ignored_process(name):
            continue
        active.setdefault(name.casefold(), name)

    if not isinstance(entries, dict):
        return []
    games = [name for key, name in active.items()
             if isinstance(entries.get(key), list) and entries[key]]
    league = next((key for key in LEAGUE_EXECUTABLES
                   if any(name.casefold() == key for name in games)), None)
    games = [name for name in games
             if name.casefold() not in LEAGUE_EXECUTABLES or name.casefold() == league]
    grouped = {}
    for name in games:
        records = entries.get(name.casefold(), [])
        identity = str(records[0].get('id') or normalize_name(records[0].get('name'))) if len(records) == 1 else 'process:' + name.casefold()
        previous = grouped.get(identity)
        if previous is None or _process_preference(name, records[0].get('name', '') if records else '') > _process_preference(previous):
            grouped[identity] = name
    return sorted(grouped.values(), key=str.casefold)


def parse_detectable_index(payload):
    index = {}
    for app in payload if isinstance(payload, list) else []:
        if not isinstance(app, dict):
            continue
        game_name = str(app.get('name') or '').strip()
        if not game_name:
            continue
        aliases = [str(a).strip() for a in app.get('aliases', []) if isinstance(a, str) and a.strip()]
        entry = {'name': game_name, 'aliases': aliases[:8], 'id': str(app.get('id') or '')}
        for exe in app.get('executables') or []:
            if not isinstance(exe, dict):
                continue
            if str(exe.get('os') or '').casefold() != 'win32':
                continue
            if exe.get('arguments'):
                continue
            executable = sanitize_executable(exe.get('name'))
            if (game_name.casefold() == 'league of legends'
                    and executable.casefold() not in LEAGUE_EXECUTABLES):
                continue
            is_league_lobby = (game_name.casefold() == 'league of legends'
                               and executable.casefold() == 'leagueclient.exe')
            if bool(exe.get('is_launcher', exe.get('isLauncher', False))) and not is_league_lobby:
                continue
            key = executable.casefold()
            if not key or is_launcher_executable(executable):
                continue
            bucket = index.setdefault(key, [])
            if all(item.get('name', '').casefold() != game_name.casefold() for item in bucket):
                bucket.append(entry)
    for value in index.values():
        value.sort(key=lambda item: item.get('name', '').casefold())
    return index


def _candidate_identity_score(category, game_name, aliases=None, process_name='', keyword=''):
    """Score whether a CHZZK category actually describes the detected game.

    This intentionally ignores CHZZK/Studio search rank bonuses.  Search endpoints may
    return a valid but unrelated category for short names (for example R.E.P.O. ->
    RePOP).  Identity has to be established from the Discord game name/aliases or the
    executable stem before a category is eligible for automatic selection.
    """
    aliases = aliases or []
    if edition_conflict([game_name, *aliases], category):
        return 0
    values = [str(game_name or '').strip()]
    values.extend(str(a).strip() for a in aliases if str(a).strip())
    stem = process_basename(process_name)
    if stem.casefold().endswith('.exe'):
        stem = stem[:-4]
    if stem:
        values.append(stem)
    if keyword:
        values.append(str(keyword).strip())

    targets = {normalize_name(v) for v in values if normalize_name(v)}
    target_tokens = {
        normalize_name(token)
        for value in values
        for token in tokenize(value)
        if len(normalize_name(token)) >= 3
    }
    if not targets and not target_tokens:
        return 0

    category_id_text = str(category.get('categoryId') or '').replace('_', ' ').replace('-', ' ')
    category_value = str(category.get('categoryValue') or '')
    candidate_compacts = {
        normalize_name(category_id_text),
        normalize_name(category_value),
    }
    candidate_compacts.discard('')
    candidate_tokens = {
        normalize_name(token)
        for token in [*tokenize(category_id_text), *tokenize(category_value)]
        if normalize_name(token)
    }

    best = 0
    # Exact meaningful token overlap is strong evidence for mixed/localized names,
    # e.g. 'PUBG: BATTLEGROUNDS' ↔ 'PUBG: 배틀그라운드'.
    for token in target_tokens:
        if token in candidate_tokens or token in candidate_compacts:
            best = max(best, 540)

    for target in targets:
        if target in candidate_compacts:
            best = max(best, 600)
        if target in candidate_tokens:
            best = max(best, 540)

        # Short compact names such as REPO, Rust, LoL, etc. are too collision-prone
        # for substring/fuzzy matching.  They require an exact compact or token match.
        if len(target) < 6:
            continue

        for candidate in candidate_compacts:
            if not candidate:
                continue
            if target in candidate or candidate in target:
                length_ratio = min(len(target), len(candidate)) / max(len(target), len(candidate))
                if length_ratio >= 0.72:
                    best = max(best, 350)
            ratio = SequenceMatcher(None, target, candidate).ratio()
            if ratio >= 0.90:
                best = max(best, 420)
            elif ratio >= 0.84:
                best = max(best, 340)
            elif ratio >= 0.78:
                best = max(best, 280)

        for token in candidate_tokens:
            if not token:
                continue
            if target == token:
                best = max(best, 540)
            elif len(token) >= 5 and (target in token or token in target):
                length_ratio = min(len(target), len(token)) / max(len(target), len(token))
                if length_ratio >= 0.72:
                    best = max(best, 360)

    return best


def _score_candidate(category, rank, normalized_targets, target_tokens, keyword):
    """Legacy/manual scorer kept for compatibility with helper functions.

    Automatic discovery uses _candidate_identity_score() below so Studio verification
    cannot turn an unrelated fuzzy result into a confident game match.
    """
    value = str(category.get('categoryValue') or '')
    normalized_value = normalize_name(value)
    value_tokens = set(tokenize(value))
    keyword_norm = normalize_name(keyword)

    score = min(90, max(0, int(category.get('_smartScore') or 0)))
    if category.get('categoryType') == 'GAME':
        score += 16
    score += max(0, 32 - rank * 3)
    if normalized_value and normalized_value in normalized_targets:
        score += 130
    if keyword_norm and keyword_norm == normalized_value:
        score += 42
    for target in normalized_targets:
        if not target or target == normalized_value:
            continue
        if len(target) >= 6 and (target in normalized_value or normalized_value in target):
            score += 34
            break

    if target_tokens and value_tokens:
        overlap = len(target_tokens & value_tokens)
        if overlap:
            score += overlap * 16

    return score


def best_category_match(game_name, aliases, categories, keyword=''):
    options = [c for c in categories if isinstance(c, dict)
               and c.get('categoryType') in ('GAME', 'ETC', 'SPORTS')
               and c.get('categoryId') and c.get('categoryValue')]
    if not options:
        return None

    ranked = []
    for rank, category in enumerate(options):
        identity = _candidate_identity_score(category, game_name, aliases, '', keyword)
        if identity < 280:
            continue
        score = identity + min(90, max(0, int(category.get('_smartScore') or 0))) + max(0, 20 - rank)
        item = dict(category)
        item['_identityScore'] = identity
        ranked.append((score, item))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return None

    best_score, best_category = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else -10**9
    margin = best_score - second_score
    confident = len(ranked) == 1 and int(best_category.get('_identityScore') or 0) >= 420
    return {
        'category': best_category,
        'score': best_score,
        'margin': margin,
        'confident': confident,
        'count': len(ranked),
    }


def choose_category(game_name, aliases, categories, keyword='', aggressive=False):
    match = best_category_match(game_name, aliases, categories, keyword)
    if not match:
        return None
    # Never use aggressive mode to accept a weak identity match.  It may only accept a
    # single already-safe candidate; multiple candidates belong in the choice dialog.
    if match['count'] == 1 and match['confident']:
        return match['category']
    return None


def _coerce_rule(value):
    if isinstance(value, Rule):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return Rule(**value)
    except Exception:
        return None


def _rule_process_keys(values):
    keys = set()
    for item in values if isinstance(values, list) else []:
        rule = _coerce_rule(item)
        if not rule:
            continue
        for value in rule.processes:
            process = process_basename(value)
            if process:
                keys.add(process.casefold())
    return keys


def _process_preference(process, game_name=''):
    """Prefer the actual game binary over test/BattleEye/helper wrappers."""
    name = process_basename(process)
    stem = name[:-4] if name.casefold().endswith('.exe') else name
    compact = re.sub(r'[^a-z0-9]+', '', stem.casefold())
    score = 100
    if compact.startswith('exec'):
        score -= 35
    for token in ('test', 'server', 'battleye', 'beservice', 'anticheat', 'helper', 'bootstrap'):
        if token in compact:
            score -= 50
    if compact.endswith('be') or '_be' in stem.casefold() or '-be' in stem.casefold():
        score -= 60
    game_compact = normalize_name(game_name)
    if game_compact and compact and (compact == game_compact or compact in game_compact or game_compact in compact):
        score += 18
    # When scores tie, prefer the simpler/shorter executable name.
    return (score, -len(name))


def _merge_rule_processes(rules):
    """Collapse auto rules that target the same CHZZK category into one row.

    Multiple executables are kept as aliases so detection still works.  This is
    important for games such as PUBG where Discord exposes TslGame.exe,
    TslGame_BE.exe and test/helper executables for the same CHZZK category.
    """
    grouped = []
    positions = {}
    for rule in rules:
        game_key = normalize_name(rule.game_name or rule.category_name)
        key = (rule.category_type, rule.category_id, game_key)
        # If Discord labels variants such as "PUBG: Test Server" differently but CHZZK
        # resolves them to one category, category identity is authoritative for grouping.
        fallback = (rule.category_type, rule.category_id)
        pos = positions.get(key)
        if pos is None:
            pos = positions.get(fallback)
        if pos is None:
            positions[key] = len(grouped)
            positions[fallback] = len(grouped)
            grouped.append(rule)
            continue

        current = grouped[pos]
        process_names = list(current.processes)
        for name in rule.processes:
            if name.casefold() not in {p.casefold() for p in process_names}:
                process_names.append(name)

        candidates = process_names
        primary = max(candidates, key=lambda x: _process_preference(x, current.game_name or rule.game_name))
        aliases = tuple(p for p in candidates if p.casefold() != primary.casefold())
        game_name = current.game_name or rule.game_name
        source = current.match_source or rule.match_source
        grouped[pos] = Rule(
            primary,
            current.category_id,
            current.category_name,
            current.category_type,
            game_name,
            source,
            aliases,
        )
    return grouped


def cleanup_auto_mappings(auto_rules, auto_pending, manual_rules=None):
    manual_keys = _rule_process_keys(manual_rules or [])
    cleaned_rules = []
    seen_processes = set()
    removed_rules = 0

    for item in auto_rules if isinstance(auto_rules, list) else []:
        rule = _coerce_rule(item)
        if not rule:
            removed_rules += 1
            continue

        valid_processes = []
        for value in league_rule_processes(rule):
            process = process_basename(value)
            if not process or is_ignored_process(process):
                continue
            if process.casefold() in manual_keys:
                continue
            if process.casefold() in seen_processes:
                continue
            valid_processes.append(process)

        if not valid_processes:
            removed_rules += 1
            continue

        verified = VERIFIED_EXECUTABLE_COMPATIBILITY.get(valid_processes[0].casefold(), {})
        known_names = [verified.get('name', ''), *verified.get('aliases', [])]
        compatibility_aliases = (verified.get('aliases', []) if verified and normalize_name(rule.game_name)
                                 in {normalize_name(n) for n in known_names if n} else [])
        if normalize_name(rule.game_name) == normalize_name(valid_processes[0][:-4]):
            compatibility_aliases = [*compatibility_aliases,
                                     *LOCALIZED_SEARCH_OVERRIDES.get(valid_processes[0].casefold(), ())]
        # Remove old auto-generated mappings that are not identity-safe. Explicit
        # category choices are preserved because they represent a user's decision.
        if (rule.game_name and '사용자 카테고리 선택' not in str(rule.match_source or '') and
                _candidate_identity_score(
                    {
                        'categoryId': rule.category_id,
                        'categoryValue': rule.category_name,
                        'categoryType': rule.category_type,
                    },
                    rule.game_name,
                    compatibility_aliases,
                    valid_processes[0],
                    rule.game_name,
                ) < 420):
            removed_rules += 1
            continue

        primary = max(valid_processes, key=lambda x: _process_preference(x, rule.game_name))
        aliases = tuple(p for p in valid_processes if p.casefold() != primary.casefold())
        normalized = Rule(
            primary,
            rule.category_id,
            rule.category_name,
            rule.category_type,
            rule.game_name,
            rule.match_source,
            aliases,
        )
        cleaned_rules.append(normalized)
        seen_processes.update(p.casefold() for p in normalized.processes)

    before_merge = len(cleaned_rules)
    cleaned_rules = _merge_rule_processes(cleaned_rules)
    removed_rules += max(0, before_merge - len(cleaned_rules))

    covered_keys = set(manual_keys)
    for rule in cleaned_rules:
        covered_keys.update(p.casefold() for p in rule.processes)

    cleaned_pending = []
    seen_pending = set()
    removed_pending = 0
    for item in auto_pending if isinstance(auto_pending, list) else []:
        if not isinstance(item, dict):
            removed_pending += 1
            continue
        process = process_basename(item.get('process', ''))
        reason = str(item.get('reason') or '').strip() or 'category-ambiguous'
        if not process or is_ignored_process(process):
            removed_pending += 1
            continue
        process_key = process.casefold()
        if process_key in manual_keys or (process_key in covered_keys and reason != 'multi-game'):
            removed_pending += 1
            continue
        key = (process_key, reason)
        if key in seen_pending:
            removed_pending += 1
            continue
        seen_pending.add(key)
        games = [str(name).strip() for name in item.get('games', []) if str(name).strip()]
        value = dict(item)
        value['process'] = process
        value['reason'] = reason
        value['games'] = games[:5]
        cleaned_pending.append(value)

    return cleaned_rules, cleaned_pending, {'rules': removed_rules, 'pending': removed_pending}


class DiscordAutoMapper:
    def __init__(self, cache_file, refresh_seconds=24 * 60 * 60,
                 aggressive_resolve=True, resolve_shared_executable=False):
        self.cache_file = Path(cache_file)
        self.refresh_seconds = int(refresh_seconds)
        self.aggressive_resolve = bool(aggressive_resolve)
        self.resolve_shared_executable = bool(resolve_shared_executable)
        self.updated_at = 0.0
        self.entries = {}
        self._loaded = False
        self._retry_at = 0.0
        self._last_index_error = ''
        self._compatibility_ready = False
        self._search_cache = OrderedDict()
        self.observer = None
        self.user_aliases = {}
        self.category_cache = None
        self.category_ttl = 21600
        self.cancelled = lambda: False
        self.last_search_error = ''
        self._game_failures = {}
        self.enrich_game = None

    def load_cache(self):
        if self._loaded:
            return
        self._loaded = True
        if not self.cache_file.exists():
            return
        try:
            data = json.loads(self.cache_file.read_text(encoding='utf-8'))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        raw_entries = data.get('entries')
        if not isinstance(raw_entries, dict):
            return
        parsed = {}
        for key, value in raw_entries.items():
            if not isinstance(key, str) or not isinstance(value, list):
                continue
            executable = sanitize_executable(key)
            if not executable or is_launcher_executable(executable):
                continue
            records = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('name') or '').strip()
                if not name:
                    continue
                aliases = [str(a).strip() for a in item.get('aliases', []) if isinstance(a, str) and a.strip()]
                records.append({'name': name, 'aliases': aliases[:8], 'id': str(item.get('id') or '')})
            if records:
                parsed[executable.casefold()] = records
        self.entries = parsed
        self.updated_at = float(data.get('updated_at') or 0.0)

    def save_cache(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {'updated_at': self.updated_at, 'entries': self.entries}
        temp = self.cache_file.with_suffix('.tmp')
        temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        temp.replace(self.cache_file)

    def refresh(self):
        response = requests.get(DISCORD_DETECTABLE_URL, timeout=(5, 15))
        response.raise_for_status()
        payload = response.json()
        index = parse_detectable_index(payload)
        if not index:
            raise RuntimeError('Discord 목록에 실행 파일 정보가 없습니다.')
        self.entries = with_verified_executable_compatibility(with_game_client_compatibility(index))
        self._compatibility_ready = True
        self.clear_search_cache()
        self.updated_at = time.time()
        self.save_cache()

    def ensure_index(self):
        self.load_cache()
        if not self._compatibility_ready:
            self.entries = with_verified_executable_compatibility(with_game_client_compatibility(self.entries))
            self._compatibility_ready = True
        stale = (time.time() - self.updated_at) >= self.refresh_seconds if self.updated_at else True
        if not self.entries:
            stale = True
        if not stale:
            return {'refreshed': False, 'used_cache': True, 'error': ''}
        if time.time() < self._retry_at:
            return {'refreshed': False, 'used_cache': bool(self.updated_at), 'error': self._last_index_error}
        try:
            self.refresh()
            self._retry_at = 0.0
            self._last_index_error = ''
            return {'refreshed': True, 'used_cache': False, 'error': ''}
        except Exception as e:
            self._retry_at = time.time() + 60
            self._last_index_error = str(e)
            if self.entries:
                return {'refreshed': False, 'used_cache': True, 'error': str(e)}
            return {'refreshed': False, 'used_cache': False, 'error': str(e)}

    def clear_search_cache(self):
        self._search_cache.clear()

    def _cached_search(self, keyword, search):
        key = str(keyword).strip().casefold()
        now = time.monotonic()
        cached = self._search_cache.get(key)
        if cached and cached[0] > now:
            self._search_cache.move_to_end(key)
            if cached[2] is not None:
                raise RuntimeError(cached[2])
            return copy.deepcopy(cached[1])
        self._search_cache.pop(key, None)
        try:
            rows = search(keyword)
        except Exception as error:
            # Retain only the message, never exception tracebacks and their frames.
            delay = max(60, float(getattr(error, 'retry_after', 0) or 0))
            self._search_cache[key] = (time.monotonic() + min(3600, delay), None, str(error))
            self._trim_search_cache()
            raise
        rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
        self._search_cache[key] = (time.monotonic() + (300 if rows else 60), copy.deepcopy(rows), None)
        self._trim_search_cache()
        return rows

    def _trim_search_cache(self):
        while len(self._search_cache) > 128:
            self._search_cache.popitem(last=False)

    def _rank_game_categories(self, game, process, search):
        """Return identity-safe CHZZK category candidates for one Discord game.

        Search/Studio ranking is only a small tie-breaker.  A candidate must first match
        the Discord name, alias, or executable stem strongly enough.  This prevents
        short names such as R.E.P.O. from being silently mapped to unrelated names like
        RePOP just because CHZZK returned them near the top.
        """
        game_name = str(game.get('name') or '').strip()
        aliases = [str(a).strip() for a in game.get('aliases', []) if str(a).strip()]
        keywords = build_search_keywords(game_name, aliases, process)

        process_stem = process_basename(process)
        if process_stem.casefold().endswith('.exe'):
            process_stem = process_stem[:-4]
        normalized_game = normalize_name(game_name)
        normalized_process = normalize_name(process_stem)
        exact_game_process = (
            len(normalized_game) >= 6
            and normalized_game == normalized_process
        )

        ranked_by_key = {}
        for keyword in keywords:
            try:
                categories = search(keyword)
            except Exception as error:
                self.last_search_error = str(error)
                continue
            if self.cancelled():
                return []
            options = [c for c in categories if isinstance(c, dict)
                       and c.get('categoryType') in ('GAME', 'ETC', 'SPORTS')
                       and c.get('categoryId') and c.get('categoryValue')]
            for rank, category in enumerate(options[:30]):
                if edition_conflict([game_name, *aliases], category):
                    continue
                identity = _candidate_identity_score(category, game_name, aliases, process, keyword)

                # Localized CHZZK categories may have a Korean display name and a categoryId
                # that no longer resembles the Discord English game name.  If Discord says
                # 'VRChat', the real process is exactly 'VRChat.exe', and CHZZK/Studio produced
                # a strong Korean candidate, keep it for the single/multiple-candidate decision.
                # Short names are intentionally excluded so REPO -> RePOP cannot regress.
                smart_score = int(category.get('_smartScore') or 0)
                source = str(category.get('_matchSource') or '')
                localized_search_verified = (
                    exact_game_process
                    and contains_hangul(str(category.get('categoryValue') or ''))
                    and (smart_score >= 300 or 'Studio' in source)
                )

                # Below this threshold the result is normally considered a search coincidence.
                # The only exception is the exact game/process + strongly verified localized
                # candidate above; it is retained so one result can auto-register and two or
                # more results can be shown in the picker.
                if identity < 280:
                    if not localized_search_verified:
                        continue
                    identity = 300

                search_bonus = min(90, max(0, smart_score))
                score = identity + search_bonus + max(0, 24 - rank)
                key = (str(category.get('categoryType')), str(category.get('categoryId')))
                old = ranked_by_key.get(key)
                if old is None or score > old['score']:
                    item = dict(category)
                    item['_identityScore'] = identity
                    item['_matchScore'] = score
                    item['_matchedKeyword'] = str(item.get('_matchedKeyword') or keyword)
                    item['_discordName'] = str(item.get('_discordName') or game_name)
                    ranked_by_key[key] = {'score': score, 'identity': identity, 'category': item}

            if (game.get('steam_appid') and contains_hangul(keyword)
                    and normalize_name(keyword) == normalize_name(game.get('steam_name_ko'))
                    and any(exact_category_identity(item['category'], [keyword])
                            for item in ranked_by_key.values())):
                break

        ranked = sorted(
            ranked_by_key.values(),
            key=lambda item: (
                item['identity'],
                item['score'],
                item['category'].get('categoryValue', ''),
            ),
            reverse=True,
        )
        identity_names = [game_name, *aliases,
                          *LOCALIZED_SEARCH_OVERRIDES.get(process_basename(process).casefold(), ())]
        exact = [item for item in ranked
                 if exact_category_identity(item['category'], identity_names)]
        if exact:
            return exact[:5]
        # LoL spin-offs share words with the original title but are different games.
        if (normalize_name(game_name) == normalize_name(LEAGUE_NAMES[0])
                and process_basename(process).casefold() in LEAGUE_EXECUTABLES):
            return []
        return ranked[:5]

    def _match_game(self, game, process, search):
        game = dict(game)
        if self.enrich_game:
            game = self.enrich_game(game, process)
        if self.cancelled():
            return None
        game['aliases'] = list(dict.fromkeys([*game.get('aliases', []), *self.user_aliases.get(game.get('name', ''), [])]))
        fingerprint = json.dumps([game.get('name'), game.get('id'), game.get('aliases')], ensure_ascii=False, sort_keys=True)
        key = game_key(game, process)
        self.last_search_error = ''
        if self.observer:
            self.observer(game, process, '분석 중')
        if self.category_cache:
            cached = self.category_cache.get(key, fingerprint, self.category_ttl)
            if cached:
                category = dict(cached['category'], _verifiedAt=cached['verified_at'])
                if self.observer:
                    self.observer(game, process, '검증 중')
                return {'game': game, 'category': category, 'score': 600, 'confident': True, 'count': 1,
                        'ambiguous': False, 'candidates': [category]}
        if self.observer:
            self.observer(game, process, '검색 중')
        ranked = self._rank_game_categories(game, process, search)
        if self.observer:
            self.observer(game, process, '검증 중')
        if not ranked:
            return None

        # 치지직은 한국어 카테고리명이 핵심이므로, 대화형 선택창은 한국어 후보가
        # 실제로 2개 이상 남았을 때만 띄웁니다. 영어/기타 후보는 선택창 조건에
        # 포함하지 않습니다. 한국어 후보가 하나라도 있으면 해당 후보군을 우선합니다.
        korean_ranked = [
            item for item in ranked
            if contains_hangul(str(item.get('category', {}).get('categoryValue') or ''))
        ]
        effective_ranked = korean_ranked if korean_ranked else ranked

        top = effective_ranked[0]
        second_score = effective_ranked[1]['score'] if len(effective_ranked) > 1 else -10**9
        margin = top['score'] - second_score

        # 한국어 후보가 2개 이상일 때만 사용자에게 선택을 요청합니다.
        ambiguous = len(korean_ranked) >= 2

        identity = int(top.get('identity') or top['category'].get('_identityScore') or 0)
        confident = len(effective_ranked) == 1 and exact_category_identity(top['category'], [game.get('name'), *game.get('aliases', []), *self.user_aliases.get(game.get('name', ''), []), *LOCALIZED_SEARCH_OVERRIDES.get(process.casefold(), ())])

        # CHZZK의 localized categoryId가 Discord 영문 게임명과 직접 닮지 않는
        # 경우가 있습니다. 예: VRChat.exe / Discord 'VRChat' -> 한국어 'VR챗'.
        # 이때 단일 한국어 후보인데 identity 점수만 낮다는 이유로 대기로 보내면
        # 자동 감지의 목적을 잃습니다.
        #
        # 다만 R.E.P.O. -> RePOP처럼 짧은 문자열 오매칭을 다시 허용하지 않도록
        # 다음 조건을 모두 만족할 때만 단일 후보를 자동 확정합니다.
        #   1) 한국어 후보가 정확히 하나
        #   2) Discord 게임명과 EXE stem이 normalize 후 정확히 일치
        #   3) 이름 길이가 6자 이상 (REPO/Rust/LoL 같은 짧은 이름 제외)
        #   4) CHZZK 검색 결과가 하나뿐이라 선택창이 필요하지 않음
        process_stem = process_basename(process)
        if process_stem.casefold().endswith('.exe'):
            process_stem = process_stem[:-4]
        normalized_game = normalize_name(game.get('name') or '')
        normalized_process = normalize_name(process_stem)
        safe_single_localized = (
            not confident
            and len(korean_ranked) == 1
            and len(effective_ranked) == 1
            and len(normalized_game) >= 6
            and normalized_game == normalized_process
            and bool(top['category'].get('_autoResolvedLocalized') or 'Studio' in str(top['category'].get('_matchSource') or ''))
        )
        if safe_single_localized:
            confident = True
            top['category']['_autoResolvedLocalized'] = True

        return {
            'game': game,
            'category': top['category'],
            'score': top['score'],
            'margin': margin,
            'confident': confident,
            'count': len(effective_ranked),
            'ambiguous': ambiguous,
            'candidates': [dict(item['category']) for item in effective_ranked],
        }

    def discover(self, processes, existing_rules, search):
        existing = {process_basename(p).casefold() for rule in existing_rules for p in rule.processes}
        new_rules = []
        unresolved = []
        for process in detectable_running_processes(processes, self.entries):
            basename = process_basename(process)
            key = basename.casefold()
            if not basename or key in existing or is_ignored_process(basename):
                continue
            options = self.entries.get(key, [])
            if self.cancelled():
                break
            if not options:
                continue
            if len(options) > 1:
                if self.observer:
                    self.observer({'name': ' / '.join(o.get('name', '') for o in options[:5])}, basename, '확인 필요')
                unresolved.append({'process': basename, 'reason': 'multi-game',
                                   'games': [o.get('name', '') for o in options[:5]]})
                continue

            matches = []
            for game in options[:8]:
                match = self._match_game(game, basename, lambda keyword: self._cached_search(keyword, search))
                if match:
                    matches.append((match.get('game', game), match))

            if not matches:
                game = options[0]
                fingerprint = json.dumps([game.get('name'), game.get('id'), list(dict.fromkeys([*game.get('aliases', []), *self.user_aliases.get(game.get('name', ''), [])]))], ensure_ascii=False, sort_keys=True)
                cached = self.category_cache.get(game_key(game, basename), fingerprint, self.category_ttl, offline=True) if self.category_cache and self.last_search_error else None
                if cached and not self.cancelled():
                    matches.append((game, {'category': dict(cached['category'], _verifiedAt=cached['verified_at']), 'score': 600, 'confident': True, 'count': 1, 'ambiguous': False, 'candidates': [cached['category']]}))
            if not matches:
                if self.observer:
                    self.observer(options[0], basename, '오류' if self.last_search_error else '확인 필요', error=self.last_search_error)
                unresolved.append({
                    'process': basename,
                    'reason': 'category-not-found',
                    'games': [o.get('name', '') for o in options[:5]],
                })
                continue

            matches.sort(key=lambda item: item[1]['score'], reverse=True)
            selected_game, selected_match = matches[0]

            candidates = selected_match.get('candidates') or []
            if selected_match.get('ambiguous') and len(candidates) >= 2:
                candidate_ids = [str(c.get('categoryId') or '') for c in candidates[:5]]
                token = category_choice_process_key(basename) + '|' + '|'.join(sorted(candidate_ids))
                unresolved.append({
                    'process': basename,
                    'reason': 'category-choice',
                    'game_name': str(selected_game.get('name') or '').strip() or Path(basename).stem,
                    'games': [str(selected_game.get('name') or '').strip()],
                    'token': token,
                    'candidates': [
                        {
                            'categoryId': str(c.get('categoryId') or ''),
                            'categoryType': str(c.get('categoryType') or 'GAME'),
                            'categoryValue': str(c.get('categoryValue') or ''),
                            'posterImageUrl': c.get('posterImageUrl'),
                            'score': int(c.get('_matchScore') or c.get('_smartScore') or 0),
                            'matchSource': str(c.get('_matchSource') or 'CHZZK'),
                            'matchedKeyword': str(c.get('_matchedKeyword') or ''),
                        }
                        for c in candidates[:5]
                        if c.get('categoryId') and c.get('categoryValue')
                    ],
                })
                continue

            if not selected_match.get('confident'):
                # A weak single result is not safe to apply automatically.  Aggressive
                # mode may help game/executable resolution, but it no longer bypasses
                # category identity checks.
                unresolved.append({
                    'process': basename,
                    'reason': 'category-ambiguous',
                    'games': [str(selected_game.get('name') or '').strip()],
                })
                continue

            if self.cancelled():
                break
            selected = selected_match['category']
            merged_aliases = list(dict.fromkeys([*selected_game.get('aliases', []), *self.user_aliases.get(selected_game.get('name', ''), [])]))
            fingerprint = json.dumps([selected_game.get('name'), selected_game.get('id'), merged_aliases], ensure_ascii=False, sort_keys=True)
            if self.category_cache:
                self.category_cache.put(game_key(selected_game, basename), fingerprint, selected, selected_game)
            if self.observer:
                self.observer(selected_game, basename, '연결 완료', category_id=selected['categoryId'], category_name=selected['categoryValue'], confidence_label=f"명칭/별칭 검증 완료 · 점수 {selected_match['score']}", verified_at=__import__('datetime').datetime.now().isoformat(timespec='seconds'))
            source = str(selected.get('_matchSource') or '').strip() or 'Discord 자동 감지'
            game_name = str(selected_game.get('name') or selected.get('_discordName') or '').strip()
            korean = selected_game.get('steam_name_ko', '')
            localized = bool(korean and exact_category_identity(selected, [korean]))
            if localized:
                source = f"Steam App ID {selected_game['steam_appid']} 한국어 매칭 · {source}"
            rule = Rule(
                basename,
                selected['categoryId'],
                selected['categoryValue'],
                selected.get('categoryType', 'GAME'),
                korean if localized else game_name,
                source,
            )
            related_processes = [p for p in processes
                                 if len(self.entries.get(p.casefold(), [])) == 1
                                 and str(self.entries[p.casefold()][0].get('id') or normalize_name(self.entries[p.casefold()][0].get('name')))
                                 == str(selected_game.get('id') or normalize_name(game_name))]
            aliases = tuple(p for p in dict.fromkeys([*league_rule_processes(rule), *related_processes])
                            if p.casefold() != key and p.casefold() not in existing
                            and len(self.entries.get(p.casefold(), [])) == 1
                            and normalize_name(self.entries[p.casefold()][0].get('name', ''))
                            == normalize_name(game_name))
            rule = Rule(rule.process, rule.category_id, rule.category_name,
                        rule.category_type, rule.game_name, rule.match_source, aliases)
            new_rules.append(rule)
            existing.update(p.casefold() for p in rule.processes)
        return new_rules, unresolved



def serialize_rules(rules):
    return [asdict(rule) for rule in rules]
