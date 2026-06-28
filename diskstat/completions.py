"""Shell completion file generators for bash, zsh, and fish."""

from __future__ import annotations


BASH_COMPLETION = """\
#!/usr/bin/env bash
# Bash completion for DiskStat
# Source this file or place in /etc/bash_completion.d/

_complete_diskstat() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts=(
        "--out" "-o"
        "--open"
        "--max-nodes" "-m"
        "--format"
        "--no-color"
        "--progress"
        "--min-size"
        "--category"
        "--exclude"
        "--sort"
        "--top"
        "--filter"
        "--max-depth"
        "--dry-run"
        "--no-html"
        "--config"
        "--compare"
        "--stdin"
        "--verbose" "-v"
        "--quiet" "-q"
        "--log-file"
        "--version"
        "--help" "-h"
    )

    case "${prev}" in
        --out|--config|--compare|--log-file)
            COMPREPLY=( $(compgen -f -- "${cur}") )
            return 0
            ;;
        --format)
            COMPREPLY=( $(compgen -W "text json csv tsv html" -- "${cur}") )
            return 0
            ;;
        --sort)
            COMPREPLY=( $(compgen -W "size name" -- "${cur}") )
            return 0
            ;;
        --category)
            COMPREPLY=( $(compgen -W "folder unknown zip image video audio doc code exe font data system" -- "${cur}") )
            return 0
            ;;
    esac

    if [[ "${cur}" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts[*]}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(compgen -d -- "${cur}") )
}

complete -F _complete_diskstat diskstat
complete -F _complete_diskstat python -m diskstat
"""

ZSH_COMPLETION = """\
#compdef diskstat
# Zsh completion for DiskStat
# Place in a directory on $fpath (e.g., /usr/local/share/zsh/site-functions/)

_arguments \\
    '(-)'{-h,--help}'[Show help message and exit]' \\
    '(-)'{-V,--version}'[Show version and exit]' \\
    '(-o --out)'{-o,--out}'[Output directory]:output_dir:_files -/' \\
    '--open[Open HTML report after generation]' \\
    '(-m --max-nodes)'{-m,--max-nodes}'[Max nodes to visualize (1-500000)]:max_nodes:' \\
    '--format[Output format]:format:(text json csv tsv html)' \\
    '--no-color[Disable colored output]' \\
    '--progress[Show scan progress]' \\
    '--min-size[Minimum file size in bytes]:min_size:' \\
    '--category[Filter by category (repeatable)]:category:(folder unknown zip image video audio doc code exe font data system)' \\
    '--exclude[Exclude directory (repeatable)]:exclude:' \\
    '--sort[Sort order]:sort:(size name)' \\
    '--top[Show top N largest files (0 = all)]:top:' \\
    '--filter[Regex pattern to filter file names]:filter:' \\
    '--max-depth[Maximum scan depth]:max_depth:' \\
    '--dry-run[Scan only, do not write files]' \\
    '--no-html[Skip HTML generation (CSV only)]' \\
    '--config[Path to YAML/JSON config file]:config_file:_files' \\
    '--compare[Path to baseline CSV to compare against]:baseline:_files' \\
    '--stdin[Read paths from stdin (one per line)]' \\
    '(-v --verbose)'{-v,--verbose}'[Increase output verbosity]' \\
    '(-q --quiet)'{-q,--quiet}'[Suppress all output except errors]' \\
    '--log-file[Write structured JSON log to file]:log_file:_files' \\
    '*:path:_files -/'
"""

FISH_COMPLETION = """\
# Fish completion for DiskStat
# Place in ~/.config/fish/completions/diskstat.fish

complete -c diskstat -f

# Flags
complete -c diskstat -s h -l help -d "Show help message"
complete -c diskstat -s V -l version -d "Show version"
complete -c diskstat -s o -l out -d "Output directory" -r
complete -c diskstat -l open -d "Open HTML report after generation"
complete -c diskstat -s m -l max-nodes -d "Max nodes to visualize" -r
complete -c diskstat -l format -d "Output format" -r -a "text json csv tsv html"
complete -c diskstat -l no-color -d "Disable colored output"
complete -c diskstat -l progress -d "Show scan progress"
complete -c diskstat -l min-size -d "Minimum file size in bytes" -r
complete -c diskstat -l category -d "Filter by category" -r -a "folder unknown zip image video audio doc code exe font data system"
complete -c diskstat -l exclude -d "Exclude directory" -r
complete -c diskstat -l sort -d "Sort order" -r -a "size name"
complete -c diskstat -l top -d "Show top N files" -r
complete -c diskstat -l filter -d "Regex filter for filenames" -r
complete -c diskstat -l max-depth -d "Maximum scan depth" -r
complete -c diskstat -l dry-run -d "Scan only, don't write files"
complete -c diskstat -l no-html -d "Skip HTML generation"
complete -c diskstat -l config -d "Path to config file" -r
complete -c diskstat -l compare -d "Baseline CSV to compare" -r
complete -c diskstat -l stdin -d "Read paths from stdin"
complete -c diskstat -s v -l verbose -d "Increase verbosity"
complete -c diskstat -s q -l quiet -d "Suppress output"
complete -c diskstat -l log-file -d "Write JSON log to file" -r

# Path completion for positional arg
complete -c diskstat -f -a "(__fish_complete_directories)"
"""


def generate_completions(dest_dir: str) -> list[str]:
    """Write completion files to dest_dir. Returns list of written paths."""
    import os
    os.makedirs(dest_dir, exist_ok=True)
    files = []
    for name, content in [
        ("diskstat.bash", BASH_COMPLETION),
        ("diskstat.zsh", ZSH_COMPLETION),
        ("diskstat.fish", FISH_COMPLETION),
    ]:
        path = os.path.join(dest_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        files.append(path)
    return files
