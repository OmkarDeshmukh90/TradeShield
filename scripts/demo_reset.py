from app.database import reset_db
from scripts.demo_seed import main as seed_main


def main() -> None:
    reset_db()
    seed_main()
    print("Demo reset completed")


if __name__ == "__main__":
    main()
