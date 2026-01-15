#!/usr/bin/env python3
"""
CPET Platform 실행 스크립트
- SQLite (기본) 또는 PostgreSQL + TimescaleDB (Docker, 선택적)
- Backend (FastAPI)
- Frontend (React + Vite)

사용법: python run.py
        python run.py --postgres  # PostgreSQL 사용
종료: Ctrl+C
"""

import sys
import signal
import subprocess
import time
import atexit
from pathlib import Path

# 프로젝트 루트 경로
ROOT_DIR = Path(__file__).parent.absolute()
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
ENV_FILE = ROOT_DIR / ".env"

# 프로세스 관리
processes = []
shutting_down = False
use_postgres = "--postgres" in sys.argv  # PostgreSQL 사용 여부

# 환경 변수 (기본값)
config = {
    "DB_PORT": "5100",
    "BACKEND_HOST": "0.0.0.0",
    "BACKEND_PORT": "8100",
    "FRONTEND_PORT": "3100",
}


def load_env():
    """루트 .env 파일에서 환경 변수 로드"""
    if not ENV_FILE.exists():
        log(f".env 파일이 없습니다: {ENV_FILE}", "WARNING")
        return

    with open(ENV_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key in config:
                    config[key] = value


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

    # Docker 확인 (PostgreSQL 사용 시에만)
    if use_postgres:
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

    # Backend venv 확인
    venv_path = BACKEND_DIR / "venv"
    if not venv_path.exists():
        errors.append(f"Backend 가상환경이 없습니다. {venv_path}")

    # Frontend node_modules 확인
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
        # 가상환경 활성화 후 uvicorn 실행
        if sys.platform == "win32":
            # Windows
            activate_cmd = f'cd /d "{BACKEND_DIR}" && venv\\Scripts\\activate && uvicorn app.main:app --reload --host {host} --port {port}'
            process = subprocess.Popen(
                activate_cmd,
                shell=True,
                cwd=BACKEND_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        else:
            # macOS / Linux
            activate_cmd = f"source venv/bin/activate && uvicorn app.main:app --reload --host {host} --port {port}"
            process = subprocess.Popen(
                activate_cmd,
                shell=True,
                executable="/bin/bash",
                cwd=BACKEND_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

        processes.append(("Backend", process))
        log(f"Backend 시작됨 - http://localhost:{port}", "SUCCESS")
        log(f"API 문서 - http://localhost:{port}/docs", "INFO")
        return True
    except Exception as e:
        log(f"Backend 시작 오류: {e}", "ERROR")
        return False


def start_frontend():
    """Frontend 서버 시작"""
    port = config["FRONTEND_PORT"]
    log(f"Frontend (React + Vite) 시작 중... (포트: {port})")

    try:
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=FRONTEND_DIR,
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

    # Docker 컨테이너 중지 (선택적)
    log("Docker 컨테이너는 계속 실행됩니다.", "INFO")
    log("DB도 중지하려면: docker compose down", "INFO")

    log("모든 서비스 종료 완료", "SUCCESS")


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
    # 환경 변수 로드
    load_env()

    print()
    print("=" * 60)
    print("  CPET Platform 실행 스크립트")
    if use_postgres:
        print("  데이터베이스: PostgreSQL (Docker)")
    else:
        print("  데이터베이스: SQLite")
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
    if use_postgres:
        if not start_database():
            sys.exit(1)
    else:
        log("SQLite 사용 중 - 별도 DB 서버 불필요", "INFO")

    if not start_backend():
        stop_all()
        sys.exit(1)

    # Frontend 시작 전 잠시 대기 (Backend가 준비되도록)
    time.sleep(2)

    if not start_frontend():
        stop_all()
        sys.exit(1)

    be_port = config["BACKEND_PORT"]
    fe_port = config["FRONTEND_PORT"]

    print()
    print("=" * 60)
    log("모든 서비스가 실행 중입니다!", "SUCCESS")
    print()
    print(f"  - Backend:  http://localhost:{be_port}")
    print(f"  - API Docs: http://localhost:{be_port}/docs")
    print(f"  - Frontend: http://localhost:{fe_port}")
    print()
    print("  종료하려면 Ctrl+C를 누르세요")
    print("=" * 60)
    print()

    # 프로세스 모니터링
    monitor_processes()


if __name__ == "__main__":
    main()
