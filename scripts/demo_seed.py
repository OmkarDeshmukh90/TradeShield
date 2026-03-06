from sqlmodel import Session

from app.database import engine, init_db
from app.services.demo_seed import seed_demo_workspace


def main() -> None:
    init_db()
    with Session(engine) as session:
        payload = seed_demo_workspace(session, include_events=True)
    print("Demo seed completed")
    print(f"Client ID: {payload.get('client_id')}")
    print(f"Admin email: {payload.get('admin_email')}")
    print(f"Admin password: {payload.get('admin_password')}")


if __name__ == "__main__":
    main()
