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
        "--version"
        "--help" "-h"
    )

    case "${prev}" in
        --out|-o|--config|--compare)
            COMPREPLY=( $(compgen -f -- "${cur}") )
            return 0
            ;;
        --format)
            COMPREPLY=( $(compgen -W "text json" -- "${cur}") )
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

complete -F _complete_diskstat python
complete -F _complete_diskstat python3
