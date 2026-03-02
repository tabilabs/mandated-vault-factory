#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ALLOWED_AGPL_PREFIXES=(
  "lib/openzeppelin-contracts-upgradeable/lib/erc4626-tests/"
  "lib/openzeppelin-contracts-upgradeable/lib/halmos-cheatcodes/"
  "lib/openzeppelin-contracts-upgradeable/lib/openzeppelin-contracts/lib/erc4626-tests/"
  "lib/openzeppelin-contracts-upgradeable/lib/openzeppelin-contracts/lib/halmos-cheatcodes/"
)

violations=()

while IFS= read -r file; do
  if grep -qi "GNU AFFERO GENERAL PUBLIC LICENSE" "$file"; then
    rel="${file#"$ROOT_DIR"/}"
    allowed=false
    for prefix in "${ALLOWED_AGPL_PREFIXES[@]}"; do
      if [[ "$rel" == "$prefix"* ]]; then
        allowed=true
        break
      fi
    done

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
