$ErrorActionPreference = 'Stop'
$version = $env:RELEASE_VERSION
$tag = $env:RELEASE_TAG
$repository = $env:GITHUB_REPOSITORY
$prerelease = $env:RELEASE_PRERELEASE -eq 'true'
$releaseMode = $prerelease.ToString().ToLowerInvariant()
$makeLatest = (-not $prerelease).ToString().ToLowerInvariant()
if ($version -notmatch '^\d+\.\d+\.\d+$' -or $tag -notin @($version, "v$version")) { throw 'Invalid release version or tag.' }
$assets = Join-Path $PWD 'release-assets'
$msi = Join-Path $assets "ChzzkAutoCategory-$version.msi"
$notes = Join-Path $assets "RELEASE_NOTES-$version.md"
$checksum = Join-Path $assets 'SHA256SUMS.txt'
$metadata = Join-Path $assets 'latest.json'
$changelog = Join-Path $assets 'CHANGELOG.md'
foreach ($path in @($msi, $notes, $checksum, $metadata, $changelog)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing asset: $path" }
}
$hash = (Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLowerInvariant()
$expected = (Get-Content -LiteralPath $checksum).Trim() -split '\s+'
if ($expected[0] -ne $hash -or $expected[1] -ne "ChzzkAutoCategory-$version.msi") { throw 'The downloaded MSI checksum does not match.' }
$info = Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
if ($info.version -ne $version -or $info.sha256 -ne $hash -or $info.installerType -ne 'msi') { throw 'Release metadata does not match the tested MSI.' }
$allReleases = gh api "repos/$repository/releases?per_page=100" | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not read current releases.' }
foreach ($release in $allReleases) {
    $plain = $release.tag_name -replace '^v', ''
    if (-not $release.draft -and -not $release.prerelease -and $plain -match '^\d+\.\d+\.\d+$' -and [version]$plain -ge [version]$version) { throw 'An equal or newer stable release is already published. Increase APP_VERSION.' }
}
$existing = @($allReleases | Where-Object { $_.tag_name -eq $tag })
if ($existing.Count -eq 0) {
    gh release create $tag --repo $repository --target $env:BUILD_SOURCE_SHA --title "CHZZK Auto Category $version" --draft --notes-file $notes "--prerelease=$releaseMode"
} else {
    if (-not $existing[0].draft) { throw 'Refusing to replace an existing published release.' }
    gh release edit $tag --repo $repository --notes-file $notes "--prerelease=$releaseMode"
}
if ($LASTEXITCODE -ne 0) { throw 'Draft release creation/update failed.' }
gh release upload $tag $msi $checksum $metadata $notes $changelog --repo $repository --clobber
if ($LASTEXITCODE -ne 0) { throw 'Release asset upload failed; the release remains a draft.' }
gh release edit $tag --repo $repository --draft=false "--prerelease=$releaseMode" "--latest=$makeLatest"
if ($LASTEXITCODE -ne 0) { throw 'Publishing the tested release failed.' }

# Fetch current main so unrelated commits and next-version notes stay intact.
git fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Release published; fetching main for the changelog failed.' }
$head = (git rev-parse origin/main).Trim()
$keepPending = $head -ne $env:BUILD_SOURCE_SHA
git switch -C release-changelog origin/main
if ($LASTEXITCODE -ne 0) { throw 'Release published; changelog branch checkout failed.' }
$recordArgs = @('scripts/release_notes.py', 'record', '--version', $version, '--tag', $tag, '--notes', $notes)
if ($keepPending) { $recordArgs += '--keep-pending' }
python @recordArgs
if ($LASTEXITCODE -ne 0) { throw 'Release published; CHANGELOG generation failed.' }
git add -- CHANGELOG.md
git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    git -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' commit -m "docs: record release $tag [skip ci]"
    if ($LASTEXITCODE -ne 0) { throw 'Release published; changelog commit failed.' }
    git push origin HEAD:refs/heads/main
    if ($LASTEXITCODE -ne 0) { throw 'Release published; main changed or branch protection rejected the changelog push.' }
} elseif ($LASTEXITCODE -ne 0) { throw 'Release published; checking the changelog diff failed.' }
"Published $tag and recorded CHANGELOG.md." | Add-Content $env:GITHUB_STEP_SUMMARY
