#!/usr/bin/env python3
"""Repository entry point; installed distributions ship the same scanner."""

from moro.security.hook import check_pii_in_data, check_secrets, get_staged_files, main

__all__ = ["check_pii_in_data", "check_secrets", "get_staged_files", "main"]

if __name__ == "__main__":
    main()
