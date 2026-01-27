#!/bin/bash
# CPET Platform 로컬 개발 서버 실행

cd "$(dirname "$0")"

echo "🚀 Starting CPET Platform..."
echo ""

# Backend (port 8100)
echo "📦 Starting Backend on port 8100..."
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100 &
BACKEND_PID=$!
cd ..

sleep 2

# Frontend (port 3100)
echo "🎨 Starting Frontend on port 3100..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Services started:"
echo "   Backend:  http://localhost:8100"
echo "   Frontend: http://localhost:3100"
echo ""
echo "Press Ctrl+C to stop all services"

# Trap Ctrl+C to kill both processes
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT

# Wait for both processes
wait
