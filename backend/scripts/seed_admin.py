import os
import sys
import argparse
import getpass

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.database.db_config import ensure_users_table
from backend.services.auth_service import register_user

def seed_admin(name, email, password):
    """Controlled, non-public administration provisioning script."""
    print("=" * 60)
    print(" ChargeFindr AI — Controlled Admin User Provisioning")
    print("=" * 60)

    # 1. Ensure table exists
    ensure_users_table()

    # 2. Register user with role='admin'
    result, status_code = register_user(
        full_name=name,
        email=email,
        password=password,
        role="admin",
        is_controlled_provision=True
    )

    if status_code == 201:
        u = result["user"]
        print("[SUCCESS] Admin user provisioned successfully!")
        print(f"  User ID : #{u['user_id']}")
        print(f"  Name    : {u['full_name']}")
        print(f"  Email   : {u['email']}")
        print(f"  Role    : {u['role']}")
        print("=" * 60)
        return True
    elif status_code == 409:
        print(f"[NOTICE] {result.get('error')}")
        print("=" * 60)
        return True
    else:
        print(f"[ERROR] Failed to provision admin user (HTTP {status_code}): {result.get('error')}")
        print("=" * 60)
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed an administrator user for ChargeFindr AI.")
    parser.add_argument("--name", default="System Administrator", help="Admin Full Name")
    parser.add_argument("--email", default="admin@chargefindr.local", help="Admin Email Address")
    parser.add_argument(
        "--password",
        default=None,
        help="Admin Password (defaults to $ADMIN_INITIAL_PASSWORD or interactive prompt if omitted)"
    )
    args = parser.parse_args()

    # Password Resolution Order:
    # 1. CLI argument (--password)
    # 2. Environment variable (ADMIN_INITIAL_PASSWORD)
    # 3. Interactive secure console prompt (getpass)
    admin_password = args.password
    if not admin_password:
        admin_password = os.getenv("ADMIN_INITIAL_PASSWORD")
    if not admin_password:
        try:
            admin_password = getpass.getpass("Enter Administrator Password: ")
        except (KeyboardInterrupt, EOFError):
            print("\n[ABORTED] Password input cancelled.")
            sys.exit(1)

    seed_admin(args.name, args.email, admin_password)

