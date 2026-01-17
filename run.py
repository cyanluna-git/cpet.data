#!/usr/bin/env python3
"""
CPET Platform 실행 스크립트
- PostgreSQL + TimescaleDB (Docker)
- Backend (FastAPI)
- Frontend (React + Vite)

사용법:
  python run.py           # 모든 서비스 실행 (db + backend + frontend)
  python run.py db        # DB만 실행
  python run.py backend   # Backend만 실행
  python run.py frontend  # Frontend만 실행
  
종료: Ctrl+C
"""

import sys
import signal
import subprocess
import time
import atexit
import argparse
from pathlib import Path

# 프로젝트 루트 경로
ROOT_DIR = Path(__file__).parent.absolute()
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
ENV_FILE = ROOT_DIR / ".env"

# 프로세스 관리
processes = []
shutting_down = False
run_mode = "all"  # all, db, backend, frontend

# 환경 변수 (기본값 - .env에서 덮어쓰기됨)
config = {
    "DB_PORT": "5100",
    "BACKEND_HOST": "0.0.0.0",
    "BACKEND_PORT": "8100",
    "FRONTEND_PORT": "3100",
    "VITE_API_URL": "",  # 프론트엔드에서 사용할 API URL
}


def load_env():
    """루트 .env 파일에서 환경 변수 로드"""
    if not ENV_FILE.exists():
        log(f".env 파일이 없습니다: {ENV_FILE}", "WARNING")
        return

    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # 모든 환경 변수를 config에 저장 (필요한 것만)
                if key in config or key.startswith("VITE_") or key.startswith("DB_"):
                    config[key] = value
    
    # VITE_API_URL이 없으면 BACKEND_PORT로 생성
    if not config.get("VITE_API_URL"):
        config["VITE_API_URL"] = f"http://localhost:{config['BACKEND_PORT']}"


def log(message: str, level: str = "INFO"):
    """로그 출력"""
    colors = {
        "INFO": "\033[94m",  # Blue
        "SUCCESS": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "RESET": "\033[0m",
    }
    color = colors.get(level, colors["INFO"])
    reset = colors["RESET"]
    print(f"{color}[{level}]{reset} {message}")


def check_requirements():
    """필수 요구사항 확인"""
    errors = []

    # .env 파일 확인
    if not ENV_FILE.exists():
        errors.append(f".env 파일이 없습니다. {ENV_FILE}")

    # Docker 확인 (DB 실행 시에만)
    if run_mode in ["all", "db"]:
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            errors.append("Docker가 설치되어 있지 않습니다.")

        # docker-compose 확인
        try:
            subprocess.run(
                ["docker", "compose", "version"], capture_output=True, check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                subprocess.run(
                    ["docker-compose", "--version"], capture_output=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                errors.append("Docker Compose가 설치되어 있지 않습니다.")

    # Backend venv 확인 (Backend 실행 시에만)
    if run_mode in ["all", "backend"]:
        venv_path = ROOT_DIR / ".venv"
        if not venv_path.exists():
            errors.append(f"Backend 가상환경이 없습니다. {venv_path}")

    # Frontend node_modules 확인 (Frontend 실행 시에만)
    if run_mode in ["all", "frontend"]:
        node_modules = FRONTEND_DIR / "node_modules"
        if not node_modules.exists():
            errors.append(
                f"Frontend 의존성이 없습니다. 'cd frontend && npm install' 실행 필요"
            )

    if errors:
        for err in errors:
            log(err, "ERROR")
        return False

    return True


def start_database():
    """Docker로 PostgreSQL + TimescaleDB 시작"""
    log(f"PostgreSQL + TimescaleDB 시작 중... (포트: {config['DB_PORT']})")

    try:
        # docker compose 우선 시도
        result = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # docker-compose 시도
            result = subprocess.run(
                ["docker-compose", "up", "-d"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
            )

        if result.returncode == 0:
            log("PostgreSQL + TimescaleDB 시작됨", "SUCCESS")
            # DB 준비 대기
            time.sleep(2)
            return True
        else:
            log(f"DB 시작 실패: {result.stderr}", "ERROR")
            return False
    except Exception as e:
        log(f"DB 시작 오류: {e}", "ERROR")
        return False


def start_backend():
    """Backend 서버 시작 (가상환경에서 실행)"""
    host = config["BACKEND_HOST"]
    port = config["BACKEND_PORT"]
    log(f"Backend (FastAPI) 시작 중... (포트: {port})")

    try:
        # 가상환경의 python을 직접 사용
        if sys.platform == "win32":
            # Windows
            venv_python = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
        else:
            # macOS / Linux
            venv_python = ROOT_DIR / ".venv" / "bin" / "python"
        
        # 환경 변수를 프로세스에 전달
        import os
        env = os.environ.copy()
        # .env에서 로드한 설정을 환경 변수로 전달
        for key, value in config.items():
            if key.startswith("DB_") or key in ["BACKEND_HOST", "BACKEND_PORT", "SECRET_KEY", "DATABASE_URL"]:
                env[key] = str(value)
        
        process = subprocess.Popen(
            [str(venv_python), "-m", "uvicorn", "app.main:app", "--reload", "--host", host, "--port", port],
            cwd=BACKEND_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        processes.append(("Backend", process))
        log(f"Backend 시작됨 - http://localhost:{port}", "SUCCESS")
        log(f"API 문서 - http://localhost:{port}/api/docs", "INFO")
        return True
    except Exception as e:
        log(f"Backend 시작 오류: {e}", "ERROR")
        return False


def start_frontend():
    """Frontend 서버 시작"""
    port = config["FRONTEND_PORT"]
    log(f"Frontend (React + Vite) 시작 중... (포트: {port})")

    try:
        # 환경 변수를 프로세스에 전달
        import os
        env = os.environ.copy()
        # 프론트엔드에 필요한 환경 변수 전달
        env["FRONTEND_PORT"] = str(port)
        env["BACKEND_PORT"] = config["BACKEND_PORT"]
        env["VITE_API_URL"] = config["VITE_API_URL"]
        
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=FRONTEND_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        processes.append(("Frontend", process))
        log(f"Frontend 시작됨 - http://localhost:{port}", "SUCCESS")
        return True
    except Exception as e:
        log(f"Frontend 시작 오류: {e}", "ERROR")
        return False


def stop_all():
    """모든 서비스 종료"""
    global shutting_down
    if shutting_down:
        return
    shutting_down = True

    print()
    log("서비스 종료 중...", "WARNING")

    # 프로세스 종료
    for name, process in processes:
        if process.poll() is None:  # 아직 실행 중이면
            log(f"{name} 종료 중...")
            process.terminate()
            try:
                process.wait(timeout=5)
                log(f"{name} 종료됨", "SUCCESS")
            except subprocess.TimeoutExpired:
                log(f"{name} 강제 종료", "WARNING")
                process.kill()

    # Docker 컨테이너 정보 출력
    if run_mode in ["all", "db"]:
        log("Docker 컨테이너는 계속 실행됩니다.", "INFO")
        log("DB도 중지하려면: docker compose down", "INFO")
    
    log("서비스 종료 완료", "SUCCESS")


def signal_handler(_signum, _frame):
    """Ctrl+C 시그널 핸들러"""
    stop_all()
    sys.exit(0)


def monitor_processes():
    """프로세스 모니터링 및 출력"""
    try:
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    log(
                        f"{name} 프로세스가 종료되었습니다 (코드: {process.returncode})",
                        "ERROR",
                    )
                    stop_all()
                    sys.exit(1)

                # 출력 읽기 (non-blocking하게 처리)
                try:
                    line = process.stdout.readline()
                    if line:
                        # 색상 코드 추가
                        if name == "Backend":
                            prefix = "\033[96m[BE]\033[0m"
                        else:
                            prefix = "\033[95m[FE]\033[0m"
                        print(f"{prefix} {line.rstrip()}")
                except Exception:
                    pass

            time.sleep(0.1)
    except KeyboardInterrupt:
        pass


def main():
    """메인 실행 함수"""
    global run_mode
    
    # 커맨드 라인 인자 파싱
    parser = argparse.ArgumentParser(
        description="CPET Platform 실행 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python run.py           # 모든 서비스 실행 (db + backend + frontend)
  python run.py db        # DB(Docker) 컨테이너만 실행
  python run.py backend   # Backend(FastAPI)만 실행
  python run.py frontend  # Frontend(React+Vite)만 실행
        """
    )
    parser.add_argument(
        "service",
        nargs="?",
        default="all",
        choices=["all", "db", "backend", "frontend"],
        help="실행할 서비스 (기본: all)"
    )
    args = parser.parse_args()
    run_mode = args.service
    
    # 환경 변수 로드
    load_env()

    print()
    print("=" * 60)
    print("  CPET Platform 실행 스크립트")
    
    # 실행 모드 표시
    if run_mode == "all":
        print("  실행: 모든 서비스 (DB + Backend + Frontend)")
    elif run_mode == "db":
        print("  실행: DB (PostgreSQL + TimescaleDB, Docker)")
    elif run_mode == "backend":
        print("  실행: Backend (FastAPI)")
    elif run_mode == "frontend":
        print("  실행: Frontend (React + Vite)")
    
    print("  종료: Ctrl+C")
    print("=" * 60)
    print()

    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(stop_all)

    # 요구사항 확인
    if not check_requirements():
        log("필수 요구사항을 확인해 주세요.", "ERROR")
        sys.exit(1)

    log("모든 요구사항 확인됨", "SUCCESS")
    print()

    # 서비스 시작
    services_started = []
    
    # DB 시작
    if run_mode in ["all", "db"]:
        if not start_database():
            sys.exit(1)
        services_started.append(f"DB (포트: {config['DB_PORT']})")
        
        # DB만 실행하는 경우
        if run_mode == "db":
            print()
            print("=" * 60)
            log("DB 컨테이너가 실행 중입니다!", "SUCCESS")
            print()
            print(f"  - PostgreSQL: localhost:{config['DB_PORT']}")
            print()
            print("  중지하려면: docker compose down")
            print("=" * 60)
            print()
            return  # DB만 실행하고 종료

    # Backend 시작
    if run_mode in ["all", "backend"]:
        if not start_backend():
            stop_all()
            sys.exit(1)
        services_started.append(f"Backend (포트: {config['BACKEND_PORT']})")
        
        # Backend만 실행하는 경우
        if run_mode == "backend":
            be_port = config["BACKEND_PORT"]
            print()
            print("=" * 60)
            log("Backend가 실행 중입니다!", "SUCCESS")
            print()
            print(f"  - Backend:  http://localhost:{be_port}")
            print(f"  - API Docs: http://localhost:{be_port}/api/docs")
            print()
            print("  종료하려면 Ctrl+C를 누르세요")
            print("=" * 60)
            print()
            monitor_processes()
            return

    # Frontend 시작
    if run_mode in ["all", "frontend"]:
        # Frontend 시작 전 잠시 대기 (all 모드일 때 Backend가 준비되도록)
        if run_mode == "all":
            time.sleep(2)
        
        if not start_frontend():
            stop_all()
            sys.exit(1)
        services_started.append(f"Frontend (포트: {config['FRONTEND_PORT']})")
        
        # Frontend만 실행하는 경우
        if run_mode == "frontend":
            fe_port = config["FRONTEND_PORT"]
            print()
            print("=" * 60)
            log("Frontend가 실행 중입니다!", "SUCCESS")
            print()
            print(f"  - Frontend: http://localhost:{fe_port}")
            print(f"  - Backend API: {config['VITE_API_URL']}")
            print()
            print("  종료하려면 Ctrl+C를 누르세요")
            print("=" * 60)
            print()
            monitor_processes()
            return

    # 모든 서비스 실행 시
    be_port = config["BACKEND_PORT"]
    fe_port = config["FRONTEND_PORT"]

    print()
    print("=" * 60)
    log("모든 서비스가 실행 중입니다!", "SUCCESS")
    print()
    print(f"  - Database: localhost:{config['DB_PORT']}")
    print(f"  - Backend:  http://localhost:{be_port}")
    print(f"  - API Docs: http://localhost:{be_port}/api/docs")
    print(f"  - Frontend: http://localhost:{fe_port}")
    print()
    print("  종료하려면 Ctrl+C를 누르세요")
    print("=" * 60)
    print()

    # 프로세스 모니터링
    monitor_processes()


if __name__ == "__main__":
    main()
