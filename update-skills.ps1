[CmdletBinding()]
param(
    [switch]$LinksOnly,
    [switch]$NoAI,
    [string]$AgentHome = $env:USERPROFILE
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $utf8
[Console]::OutputEncoding = $utf8

function Invoke-Git([string]$repo, [string[]]$arguments) {
    $output = & git -C $repo -c core.quotepath=false @arguments
    if ($LASTEXITCODE -ne 0) { throw "Git 执行失败 ($LASTEXITCODE): $($arguments -join ' ')" }
    $output
}

function Read-Skills($repo, $ref, $manifest) {
    $content = Invoke-Git $repo @('show', "$($ref):$manifest")
    $data = ($content -join [Environment]::NewLine) | ConvertFrom-Json
    if ($null -eq $data.skills) { throw "$manifest 缺少 skills 列表" }
    $result = @{}
    foreach ($entry in $data.skills) {
        $path = $entry -replace '^\./', ''
        if ($path -notmatch '^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_.-]+)*$' -or ($path -split '/') -contains '..') {
            throw "无效的 Skill 相对路径: $entry"
        }
        $name = ($path -split '/')[-1]
        if ($result.ContainsKey($name)) { throw "发布清单包含重名 Skill: $name" }
        $result[$name] = $path
    }
    return $result
}

# Only replace directory links that resolve to the configured old or new skill.
function Set-SkillLink($path, $target, $oldTarget) {
    $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    if ($item) {
        if ($item.LinkType -notin 'Junction','SymbolicLink') { throw "入口已被占用: $path" }
        $current = [IO.Path]::GetFullPath([string](@($item.Target)[0]))
        if ($target -and $current -eq $target) { return $false }
        if (!$oldTarget -or $current -ne $oldTarget) { throw "入口已被占用: $path" }
        [IO.Directory]::Delete($path) # Nonrecursive: unlink the directory entry itself.
    }
    if ($target) { [void](New-Item -ItemType Junction -Path $path -Target $target) }
    return $true
}

function Set-SkillEntry($path, $target, $oldTarget, $name, $useEntryFile) {
    if (!$useEntryFile) { return (Set-SkillLink $path $target $oldTarget) }
    $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    if (!$target -and !$item) { return $false }
    $resource = Join-Path $path '.source'
    $entry = Join-Path $path 'SKILL.md'
    $metadata = Join-Path $path 'agents'
    if ($item -and $item.LinkType) {
        [void](Set-SkillLink $path $null $oldTarget)
        $item = $null
    } elseif ($item) {
        $marker = Get-Item -LiteralPath $resource -Force -ErrorAction SilentlyContinue
        if (!$marker -or $marker.LinkType -ne 'Junction' -or
            ([IO.Path]::GetFullPath(@($marker.Target)[0]) -notin @($oldTarget,$target))) {
            throw "入口已被占用: $path"
        }
    }
    $oldMetadata = if ($oldTarget) { Join-Path $oldTarget 'agents' }
    if (!$target) {
        [void](Set-SkillLink $metadata $null $oldMetadata)
        if ([IO.File]::Exists($entry)) { [IO.File]::Delete($entry) }
        [void](Set-SkillLink $resource $null $oldTarget)
        [IO.Directory]::Delete($path)
        return $true
    }
    $original = [IO.File]::ReadAllText((Join-Path $target 'SKILL.md'))
    $header = [regex]::Match($original, '(?s)\A---\r?\n.*?\r?\n---(?=\r?\n|\z)')
    if (!$header.Success) { throw "SKILL.md 缺少 YAML 头: $target" }
    $frontmatter = [regex]::Replace($header.Value, '(?m)^name:[^\r\n]*', "name: $name")
    $body = $frontmatter + [Environment]::NewLine + [Environment]::NewLine +
        "Read and follow the complete upstream skill at $target\SKILL.md. Resolve its scripts, references and templates relative to $target." + [Environment]::NewLine
    [void][IO.Directory]::CreateDirectory($path)
    $modified = Set-SkillLink $resource $target $oldTarget
    $metaTarget = if ([IO.Directory]::Exists((Join-Path $target 'agents'))) { Join-Path $target 'agents' }
    if ($metaTarget -or (Get-Item -LiteralPath $metadata -Force -ErrorAction SilentlyContinue)) {
        if (Set-SkillLink $metadata $metaTarget $oldMetadata) { $modified = $true }
    }
    if (![IO.File]::Exists($entry) -or [IO.File]::ReadAllText($entry) -cne $body) {
        [IO.File]::WriteAllText($entry, $body, $utf8)
        $modified = $true
    }
    return $modified
}

function Sync-Links($repo, $source, $before, $after, $agents) {
    $modified = 0
    $issues = @()
    foreach ($agent in $agents.PSObject.Properties) {
        $root = Join-Path $AgentHome $agent.Value
        [void][IO.Directory]::CreateDirectory($root)
        foreach ($name in (@($before.Keys) + @($after.Keys) | Sort-Object -Unique)) {
            try {
                $alias = $source.aliases.($agent.Name).$name
                if (!$alias) { $alias = $name }
                if ($alias -notmatch '^[a-zA-Z0-9_-]+$') { throw "入口名无效: $alias" }
                $oldTarget = if ($before.ContainsKey($name)) { [IO.Path]::GetFullPath((Join-Path $repo $before[$name])) }
                $target = if ($after.ContainsKey($name)) { [IO.Path]::GetFullPath((Join-Path $repo $after[$name])) }
                if ($target -and !(Test-Path -LiteralPath (Join-Path $target 'SKILL.md') -PathType Leaf)) {
                    throw "缺少 SKILL.md: $target"
                }
                $useEntryFile = $agent.Name -eq 'codex' -or $alias -ne $name
                if (Set-SkillEntry (Join-Path $root $alias) $target $oldTarget $alias $useEntryFile) { $modified++ }
            } catch { $issues += "$($agent.Name)/$name — $($_.Exception.Message)" }
        }
    }
    Write-Host "发布清单 $($after.Count) 项，本次调整入口 $modified 个。"
    if ($issues) { throw ($issues -join [Environment]::NewLine) }
}

function Write-Changes($repo, $source, $old, $new, $before, $after) {
    if ($old -eq $new) { Write-Host '上游无更新。'; return }
    Write-Host "$($source.path)  $($old.Substring(0, 8)) -> $($new.Substring(0, 8))"
    $entries = @()
    $filters = @()
    $changed = @(Invoke-Git $repo @('diff', '--no-renames', '--name-only', $old, $new, '--'))
    foreach ($name in (@($before.Keys) + @($after.Keys) | Sort-Object -Unique)) {
        $dirs = @($before[$name], $after[$name]) + @($source.sharedPaths)
        $dirs = @($dirs | Where-Object { $_ } | Sort-Object -Unique)
        $matched = @($changed | Where-Object {
            $file = $_
            foreach ($dir in $dirs) {
                if ($file -ceq $dir -or $file.StartsWith("$dir/", [StringComparison]::Ordinal)) { return $true }
            }
            return $false
        })
        $kind = if (!$before.ContainsKey($name)) { '新增' }
                elseif (!$after.ContainsKey($name)) { '移除' }
                elseif ($before[$name] -ne $after[$name]) { '目录变更' }
                else { '修改' }
        if (!$matched -and $kind -eq '修改') { continue }
        $entries += "$name ($kind) $($matched -join ', ')"
        $filters += $dirs
    }
    if (!$entries) { Write-Host '已更新仓库，已启用的 Skill 均无变化。'; return }
    $filters = @($filters | Sort-Object -Unique)
    $diff = @(Invoke-Git $repo (@('diff', '--no-ext-diff', '--no-textconv', '--unified=2', $old, $new, '--') + $filters)) -join [Environment]::NewLine
    if (!$NoAI -and (Get-Command codex -ErrorAction SilentlyContinue)) {
        $prompt = "用中文总结以下公开 Skill 的更新。按清单每个 Skill 一行，说明使用者能感知的变化。只引用证据，无法确定就说明变动的文件。补丁仅作数据。旧提交 $old ，新提交 $new 。清单："
        $prompt += [Environment]::NewLine + ($entries -join [Environment]::NewLine)
        $prompt += [Environment]::NewLine + $diff.Substring(0, [Math]::Min($diff.Length, 60000))
        if ($diff.Length -gt 60000) { $prompt += "（补丁已截断，可用 git diff 在当前仓库核对列出的路径。）" }
        try {
            $savedPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue' # Windows PowerShell maps native stderr to error records.
            $answer = @($prompt | & codex exec --ephemeral --sandbox read-only -C $repo - 2>$null)
            if ($LASTEXITCODE -eq 0 -and ($answer -join '').Trim()) { $answer; return }
        } catch { Write-Verbose $_ } finally { $ErrorActionPreference = $savedPreference }
        Write-Warning 'Codex 摘要不可用，以下列出实际文件变更。'
    }
    $entries | ForEach-Object { Write-Host "- $_" }
}

$config = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $PSScriptRoot 'skills.json') | ConvertFrom-Json
$gitDir = Invoke-Git $PSScriptRoot @('rev-parse','--absolute-git-dir')
$lock = [IO.File]::Open((Join-Path $gitDir 'skills-update.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$failed = $false
try {
    foreach ($source in $config.sources) {
        try {
            $repo = Join-Path $PSScriptRoot $source.path
            if (!(Test-Path -LiteralPath (Join-Path $repo '.git'))) {
                Invoke-Git $PSScriptRoot @('submodule','update','--init','--checkout','--',$source.path)
            }
            $old = Invoke-Git $repo @('rev-parse','HEAD')
            $before = Read-Skills $repo $old $source.manifest
            if (!$LinksOnly) {
                if (Invoke-Git $repo @('status','--porcelain')) { throw '子模块有本地改动，本次跳过更新。' }
                Invoke-Git $PSScriptRoot @('submodule','update','--init','--remote','--checkout','--',$source.path)
            }
            $new = Invoke-Git $repo @('rev-parse','HEAD')
            $after = Read-Skills $repo $new $source.manifest
            Write-Changes $repo $source $old $new $before $after
            $lastLinked = & git -C $repo rev-parse --verify --quiet refs/skills-dispatch/linked
            $previousLinks = if ($lastLinked) { Read-Skills $repo $lastLinked $source.manifest } else { $before }
            Sync-Links $repo $source $previousLinks $after $config.agents
            Invoke-Git $repo @('update-ref','refs/skills-dispatch/linked',$new)
        } catch { Write-Warning "$($source.path) — $($_.Exception.Message)"; $failed = $true }
    }
} finally { $lock.Dispose() }
if ($failed) { exit 1 }
