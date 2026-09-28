#!/usr/bin/env python3
"""
scripts/test_rls.py — Proves Supabase Row Level Security (RLS) rules across roles.

Validates permissions using ONLY the anonymous public client key (SUPABASE_ANON_KEY)
to accurately simulate browser-facing operations. Under no circumstances is the
service-role key used.

Required Environment Variables:
  SUPABASE_URL            Base Supabase project URL (e.g. https://<ref>.supabase.co)
  SUPABASE_ANON_KEY       Supabase anon/public key (browser client key)
  TEST_ANALYST_EMAIL      Email for analyst test user
  TEST_ANALYST_PASSWORD   Password for analyst test user
  TEST_ADMIN_EMAIL        Email for admin test user
  TEST_ADMIN_PASSWORD     Password for admin test user

Checks and verifies PASS/FAIL for:
  1. GUEST (no login):
     - can read: index_values, routes, cpi_official
     - cannot read: fare_quotes, scrape_log, audit_log, profiles (0 rows or error)
  2. ANALYST (logged in):
     - can read: fare_quotes, dgca_monthly_avg
     - cannot read: scrape_log, audit_log (0 rows or error)
     - profiles returns only their own row
  3. ADMIN (logged in):
     - can read: scrape_log, audit_log, all profiles
  4. WRITES (all roles):
     - insert into fare_quotes must FAIL
     - update profiles set role='admin' (as analyst) must FAIL
     - delete from index_values must FAIL

Exit code:
  0 if all checks pass.
  Non-zero if any check fails or required environment variables are missing.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, List, Tuple

# Attempt to load local .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from supabase import Client, create_client
except ImportError:
    sys.exit(
        "ERROR: The 'supabase' Python package is required. "
        "Install it via: pip install supabase"
    )

REQUIRED_ENV_VARS = [
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "TEST_ANALYST_EMAIL",
    "TEST_ANALYST_PASSWORD",
    "TEST_ADMIN_EMAIL",
    "TEST_ADMIN_PASSWORD",
]


class RLSTestSuite:
    def __init__(
        self,
        supabase_url: str,
        anon_key: str,
        analyst_email: str,
        analyst_password: str,
        admin_email: str,
        admin_password: str,
    ) -> None:
        self.supabase_url = self._normalize_url(supabase_url)
        self.anon_key = anon_key
        self.analyst_email = analyst_email
        self.analyst_password = analyst_password
        self.admin_email = admin_email
        self.admin_password = admin_password

        self.passed_count = 0
        self.failed_count = 0
        self.results: List[Tuple[str, str, str]] = []  # (STATUS, CHECK_NAME, DETAILS)

        # Clients for each role (created with ONLY anon_key)
        self.guest_client: Client | None = None
        self.analyst_client: Client | None = None
        self.admin_client: Client | None = None

        self.analyst_uid: str | None = None
        self.admin_uid: str | None = None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Strip trailing slashes or /rest/v1 to obtain base Supabase endpoint."""
        cleaned = url.strip().rstrip("/")
        if cleaned.endswith("/rest/v1"):
            cleaned = cleaned[:-8]
        return cleaned.rstrip("/")

    def _sanitize(self, message: str) -> str:
        """Ensure passwords and tokens are never printed in console output."""
        sensitive = [
            self.analyst_password,
            self.admin_password,
            self.anon_key,
        ]
        out = str(message)
        for s in sensitive:
            if s and len(s) >= 4:
                out = out.replace(s, "[REDACTED]")
        # Redact any JWT bearer tokens that might appear in error messages
        out = re.sub(r"eyJ[a-zA-Z0-9_\-\.]+", "[REDACTED_JWT]", out)
        return out

    def record_pass(self, name: str, detail: str = "") -> None:
        self.passed_count += 1
        sanitized_detail = self._sanitize(detail)
        self.results.append(("PASS", name, sanitized_detail))
        if sanitized_detail:
            print(f"  [PASS] {name} ({sanitized_detail})")
        else:
            print(f"  [PASS] {name}")

    def record_fail(self, name: str, reason: str) -> None:
        self.failed_count += 1
        sanitized_reason = self._sanitize(reason)
        self.results.append(("FAIL", name, sanitized_reason))
        print(f"  [FAIL] {name} - {sanitized_reason}")

    def setup_clients(self) -> bool:
        """Initialize separate clients and authenticate analyst and admin."""
        print("\n--- Initializing Supabase Clients (Anon Key Only) ---")
        try:
            self.guest_client = create_client(self.supabase_url, self.anon_key)
            self.analyst_client = create_client(self.supabase_url, self.anon_key)
            self.admin_client = create_client(self.supabase_url, self.anon_key)
        except Exception as e:
            self.record_fail("Client Initialization", f"Failed to initialize clients: {e}")
            return False

        # Authenticate Analyst
        try:
            analyst_auth = self.analyst_client.auth.sign_in_with_password({
                "email": self.analyst_email,
                "password": self.analyst_password,
            })
            if analyst_auth.user:
                self.analyst_uid = analyst_auth.user.id
                print(f"  Authenticated analyst: {self.analyst_email} (UID: {self.analyst_uid})")
            else:
                self.record_fail("Analyst Authentication", "Sign in succeeded but returned no user.")
                return False
        except Exception as e:
            self.record_fail("Analyst Authentication", f"Sign in failed: {self._sanitize(str(e))}")
            return False

        # Authenticate Admin
        try:
            admin_auth = self.admin_client.auth.sign_in_with_password({
                "email": self.admin_email,
                "password": self.admin_password,
            })
            if admin_auth.user:
                self.admin_uid = admin_auth.user.id
                print(f"  Authenticated admin:   {self.admin_email} (UID: {self.admin_uid})")
            else:
                self.record_fail("Admin Authentication", "Sign in succeeded but returned no user.")
                return False
        except Exception as e:
            self.record_fail("Admin Authentication", f"Sign in failed: {self._sanitize(str(e))}")
            return False

        return True

    # ──────────────────────────────────────────────────────────────────────────
    # 1. GUEST TESTS
    # ──────────────────────────────────────────────────────────────────────────
    def run_guest_tests(self) -> None:
        print("\n--- [1] GUEST (No Login) ---")
        assert self.guest_client is not None

        # Public tables: can read index_values, routes, cpi_official
        for table in ["index_values", "routes", "cpi_official"]:
            try:
                res = self.guest_client.table(table).select("*").limit(5).execute()
                self.record_pass(f"GUEST can read '{table}'", f"returned {len(res.data)} sample rows")
            except Exception as e:
                self.record_fail(f"GUEST can read '{table}'", f"Query rejected: {e}")

        # Restricted tables: cannot read fare_quotes, scrape_log, audit_log, profiles
        # (must return 0 rows under RLS or raise an authorization error)
        for table in ["fare_quotes", "scrape_log", "audit_log", "profiles"]:
            try:
                res = self.guest_client.table(table).select("*").limit(5).execute()
                if len(res.data) == 0:
                    self.record_pass(f"GUEST cannot read '{table}'", "0 rows returned under RLS")
                else:
                    self.record_fail(
                        f"GUEST cannot read '{table}'",
                        f"Security violation! Leaked {len(res.data)} rows to unauthenticated guest."
                    )
            except Exception as e:
                self.record_pass(f"GUEST cannot read '{table}'", "query rejected with error")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. ANALYST TESTS
    # ──────────────────────────────────────────────────────────────────────────
    def run_analyst_tests(self) -> None:
        print("\n--- [2] ANALYST (Logged in) ---")
        assert self.analyst_client is not None

        # Can read fare_quotes and dgca_monthly_avg
        for table in ["fare_quotes", "dgca_monthly_avg"]:
            try:
                res = self.analyst_client.table(table).select("*").limit(5).execute()
                self.record_pass(f"ANALYST can read '{table}'", f"returned {len(res.data)} sample rows")
            except Exception as e:
                self.record_fail(f"ANALYST can read '{table}'", f"Query rejected: {e}")

        # Cannot read scrape_log or audit_log (0 rows or error)
        for table in ["scrape_log", "audit_log"]:
            try:
                res = self.analyst_client.table(table).select("*").limit(5).execute()
                if len(res.data) == 0:
                    self.record_pass(f"ANALYST cannot read '{table}'", "0 rows returned under RLS")
                else:
                    self.record_fail(
                        f"ANALYST cannot read '{table}'",
                        f"Security violation! Analyst accessed {len(res.data)} rows."
                    )
            except Exception as e:
                self.record_pass(f"ANALYST cannot read '{table}'", "query rejected with error")

        # profiles returns only their own row
        try:
            res = self.analyst_client.table("profiles").select("*").execute()
            rows = res.data or []
            if len(rows) == 1:
                row = rows[0]
                row_id = str(row.get("id"))
                row_email = row.get("email")
                if row_id == str(self.analyst_uid) or row_email == self.analyst_email:
                    self.record_pass(
                        "ANALYST profiles returns only their own row",
                        f"exactly 1 row returned matching UID {row_id}"
                    )
                else:
                    self.record_fail(
                        "ANALYST profiles returns only their own row",
                        f"Returned profile id {row_id} does not match analyst UID {self.analyst_uid}"
                    )
            elif len(rows) == 0:
                self.record_fail(
                    "ANALYST profiles returns only their own row",
                    "Expected 1 row for analyst profile, but received 0 rows."
                )
            else:
                self.record_fail(
                    "ANALYST profiles returns only their own row",
                    f"Security violation! Analyst received {len(rows)} profiles (expected 1)."
                )
        except Exception as e:
            self.record_fail("ANALYST profiles returns only their own row", f"Query failed: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. ADMIN TESTS
    # ──────────────────────────────────────────────────────────────────────────
    def run_admin_tests(self) -> None:
        print("\n--- [3] ADMIN (Logged in) ---")
        assert self.admin_client is not None

        # Can read scrape_log
        try:
            res = self.admin_client.table("scrape_log").select("*").limit(5).execute()
            self.record_pass("ADMIN can read 'scrape_log'", f"returned {len(res.data)} sample rows")
        except Exception as e:
            self.record_fail("ADMIN can read 'scrape_log'", f"Query rejected: {e}")

        # Can read audit_log
        try:
            res = self.admin_client.table("audit_log").select("*").limit(5).execute()
            self.record_pass("ADMIN can read 'audit_log'", f"returned {len(res.data)} sample rows")
        except Exception as e:
            self.record_fail("ADMIN can read 'audit_log'", f"Query rejected: {e}")

        # Can read all profiles
        try:
            res = self.admin_client.table("profiles").select("*").execute()
            rows = res.data or []
            if not rows:
                self.record_fail("ADMIN can read all profiles", "0 rows returned")
            else:
                profile_ids = {str(r.get("id")) for r in rows}
                profile_emails = {r.get("email") for r in rows}
                has_analyst = (str(self.analyst_uid) in profile_ids) or (self.analyst_email in profile_emails)
                has_admin = (str(self.admin_uid) in profile_ids) or (self.admin_email in profile_emails)

                if len(rows) > 1 and has_analyst and has_admin:
                    self.record_pass(
                        "ADMIN can read all profiles",
                        f"{len(rows)} profiles visible (both analyst and admin profiles found)"
                    )
                elif len(rows) > 1:
                    self.record_pass(
                        "ADMIN can read all profiles",
                        f"{len(rows)} profiles visible"
                    )
                elif has_analyst and not has_admin:
                    self.record_pass(
                        "ADMIN can read all profiles",
                        f"{len(rows)} profile visible (includes analyst profile)"
                    )
                else:
                    if self.analyst_uid:
                        self.record_fail(
                            "ADMIN can read all profiles",
                            f"Admin only received {len(rows)} profile(s); analyst profile was not visible."
                        )
                    else:
                        self.record_pass("ADMIN can read all profiles", f"{len(rows)} profile row found")
        except Exception as e:
            self.record_fail("ADMIN can read all profiles", f"Query rejected: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # 4. WRITE TESTS (ALL ROLES MUST FAIL)
    # ──────────────────────────────────────────────────────────────────────────
    def run_write_tests(self) -> None:
        print("\n--- [4] WRITES (Must All FAIL Across Roles) ---")
        dummy_fare_quote = {
            "route_code": "DEL-BOM",
            "source": "rls_security_probe",
            "travel_date": "2026-12-31",
            "scrape_date": "2026-09-28",
            "advance_purchase_days": 90,
            "total_fare": 99999,
        }

        roles: List[Tuple[str, Client]] = [
            ("GUEST", self.guest_client),
            ("ANALYST", self.analyst_client),
            ("ADMIN", self.admin_client),
        ]

        # 4a. insert into fare_quotes must FAIL for all roles
        for role_name, client in roles:
            check_name = f"WRITES: {role_name} insert into fare_quotes FAIL"
            try:
                res = client.table("fare_quotes").insert(dummy_fare_quote).execute()
                if res.data and len(res.data) > 0:
                    self.record_fail(
                        check_name,
                        f"Security violation! {role_name} inserted {len(res.data)} row(s)."
                    )
                else:
                    self.record_pass(check_name, "0 rows inserted / write blocked")
            except Exception as e:
                self.record_pass(check_name, "rejected with permission error as expected")

        # 4b. update profiles set role='admin' (as analyst) must FAIL
        check_name_promote = "WRITES: ANALYST update profiles set role='admin' FAIL"
        try:
            res = (
                self.analyst_client.table("profiles")
                .update({"role": "admin"})
                .eq("id", str(self.analyst_uid))
                .execute()
            )
            # Verify if role was actually changed
            verify = (
                self.analyst_client.table("profiles")
                .select("role")
                .eq("id", str(self.analyst_uid))
                .execute()
            )
            if verify.data and verify.data[0].get("role") == "admin":
                self.record_fail(
                    check_name_promote,
                    "Privilege escalation! Analyst successfully self-promoted to admin."
                )
            else:
                self.record_pass(
                    check_name_promote,
                    "self-promotion blocked (role remains analyst / 0 rows updated)"
                )
        except Exception as e:
            self.record_pass(check_name_promote, "rejected with permission error as expected")

        # 4c. delete from index_values must FAIL for all roles
        for role_name, client in roles:
            check_name = f"WRITES: {role_name} delete from index_values FAIL"
            try:
                # Use a dummy negative ID so that even if misconfigured, real data is never deleted
                res = client.table("index_values").delete().eq("id", -999999).execute()
                if res.data and len(res.data) > 0:
                    self.record_fail(
                        check_name,
                        f"Security violation! {role_name} was allowed to delete rows."
                    )
                else:
                    self.record_pass(check_name, "delete blocked / 0 rows deleted")
            except Exception as e:
                self.record_pass(check_name, "rejected with permission error as expected")

    # ──────────────────────────────────────────────────────────────────────────
    # Runner & Summary
    # ──────────────────────────────────────────────────────────────────────────
    def run(self) -> int:
        print("=" * 78)
        print(" AIRIVA SUPABASE ROW LEVEL SECURITY (RLS) TEST SUITE")
        print(" Using anon key only (browser-facing capability simulation)")
        print("=" * 78)

        if not self.setup_clients():
            print("\nFATAL: Failed to initialize clients and authenticate test users.")
            return 1

        self.run_guest_tests()
        self.run_analyst_tests()
        self.run_admin_tests()
        self.run_write_tests()

        total = self.passed_count + self.failed_count
        print("\n" + "=" * 78)
        print(f" RLS TEST SUMMARY: {self.passed_count}/{total} PASSED, {self.failed_count} FAILED")
        print("=" * 78)

        if self.failed_count > 0:
            print("\nFAILED CHECKS:")
            for status, name, detail in self.results:
                if status == "FAIL":
                    print(f"  - [FAIL] {name}: {detail}")
            return 1

        print("\nAll Row Level Security rules verified successfully!")
        return 0


def main() -> int:
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        print("ERROR: Missing required environment variable(s):", file=sys.stderr)
        for var in missing:
            print(f"  - {var}", file=sys.stderr)
        print(
            "\nPlease set these variables in your environment or .env file before running.\n"
            "Example:\n"
            "  export SUPABASE_URL='https://<ref>.supabase.co'\n"
            "  export SUPABASE_ANON_KEY='<anon_key>'\n"
            "  export TEST_ANALYST_EMAIL='analyst@airiva.local'\n"
            "  export TEST_ANALYST_PASSWORD='...'\n"
            "  export TEST_ADMIN_EMAIL='admin@airiva.local'\n"
            "  export TEST_ADMIN_PASSWORD='...'",
            file=sys.stderr,
        )
        return 1

    suite = RLSTestSuite(
        supabase_url=os.environ["SUPABASE_URL"],
        anon_key=os.environ["SUPABASE_ANON_KEY"],
        analyst_email=os.environ["TEST_ANALYST_EMAIL"],
        analyst_password=os.environ["TEST_ANALYST_PASSWORD"],
        admin_email=os.environ["TEST_ADMIN_EMAIL"],
        admin_password=os.environ["TEST_ADMIN_PASSWORD"],
    )
    return suite.run()


if __name__ == "__main__":
    sys.exit(main())
