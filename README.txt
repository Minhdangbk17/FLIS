flis_backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # Entry point của ứng dụng (Khởi tạo FastAPI app)
│   ├── api/                    # LAYER 1: ROUTER/CONTROLLER
│   │   ├── __init__.py
│   │   ├── api_v1/
│   │   │   ├── __init__.py
│   │   │   ├── api.py          # Gom tất cả router
│   │   │   └── endpoints/      # Các controller cụ thể
│   │   │       ├── __init__.py
│   │   │       ├── auth.py
│   │   │       ├── inspection.py
│   │   │       └── report.py
│   ├── core/                   # Cấu hình hệ thống (Config, Security, Constants)
│   │   ├── __init__.py
│   │   ├── config.py           # Load biến môi trường (.env)
│   │   ├── security.py         # JWT Token logic
│   │   └── exceptions.py       # Custom Exception
│   ├── db/                     # Cấu hình Database
│   │   ├── __init__.py
│   │   ├── session.py          # Tạo DB Engine & SessionLocal
│   │   └── base.py             # Import tất cả models để Alembic nhận diện
│   ├── models/                 # ORM Models (SQLAlchemy) - Mapping với Table trong DB
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── inspection.py
│   │   └── fabric.py
│   ├── schemas/                # Data Models (Pydantic) - Validate Input/Output
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── inspection.py
│   ├── repositories/           # LAYER 3: DAO LAYER (Truy vấn DB thuần túy)
│   │   ├── __init__.py
│   │   ├── base.py             # CRUD Base generic
│   │   ├── user_repo.py
│   │   └── inspection_repo.py
│   └── services/               # LAYER 2: SERVICE LAYER (Business Logic)
│       ├── __init__.py
│       ├── auth_service.py
│       └── inspection_service.py
├── alembic/                    # Quản lý Migrations DB
├── tests/                      # Unit Tests & Integration Tests
├── .env                        # Biến môi trường (Không commit lên git)
├── .env.example                # Mẫu biến môi trường
├── .dockerignore
├── Dockerfile                  # Cấu hình Docker
└── requirements.txt            # Danh sách thư viện