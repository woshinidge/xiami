from __future__ import annotations

import argparse

from xiami_core.runtime_diagnostic import (
    apply_suggested_kernel_config,
    build_runtime_diagnostic,
    format_runtime_diagnostic,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Show or apply Xiami runtime kernel diagnostics.")
    parser.add_argument("--apply", action="store_true", help="Apply the suggested real NapCat/Lagrange kernel config.")
    args = parser.parse_args()

    if args.apply:
        result = apply_suggested_kernel_config()
        print(result.detail)
        print(f"kernel={result.config.kernel.kind}")
        print(f"executable={result.config.kernel.executable}")
        print(f"working_dir={result.config.kernel.working_dir}")
        return 0 if result.ok else 1

    print("\n".join(format_runtime_diagnostic(build_runtime_diagnostic())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
