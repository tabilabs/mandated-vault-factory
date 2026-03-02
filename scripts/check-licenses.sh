#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

violations=()

while IFS= read -r file; do
  if grep -qi "GNU AFFERO GENERAL PUBLIC LICENSE" "$file"; then
    rel="${file#"$ROOT_DIR"/}"
    allowed=false
    case "$rel" in
      *"/erc4626-tests/"*|*"/halmos-cheatcodes/"*) allowed=true ;;
    esac

    if [[ "$allowed" == false ]]; then
      violations+=("$rel")
    fi
  fi
done < <(find "$ROOT_DIR" -type f \( -iname "LICENSE" -o -iname "LICENSE-*" -o -iname "COPYING" -o -iname "COPYING.*" \))

if (( ${#violations[@]} > 0 )); then
  echo "License check failed: AGPL license found outside approved paths:" >&2
  for v in "${violations[@]}"; do
    echo "  - $v" >&2
  done
  exit 1
fi

echo "License check passed: AGPL usage is within approved test/tooling paths."
