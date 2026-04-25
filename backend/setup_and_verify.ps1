Write-Host "=========================================="
Write-Host "Anti-Gravity CV Agent - Automated setup"
Write-Host "=========================================="
Write-Host ""
Write-Host "1. Waiting for Docker containers to be ready..."
# The --wait flag will block until all healthchecks pass
docker-compose up -d --build --wait

Write-Host ""
Write-Host "2. Pulling the Ollama models (this may take a while depending on your internet connection)..."
Write-Host "Pulling llama3.1:8b..."
docker exec paths_ollama ollama pull llama3.1:8b
Write-Host "Pulling nomic-embed-text..."
docker exec paths_ollama ollama pull nomic-embed-text

Write-Host ""
Write-Host "3. Applying Alembic migrations..."
# Since the backend container depends on the .env db url, we can run alembic inside it easily:
docker exec paths_backend alembic upgrade head

Write-Host ""
Write-Host "4. Testing the CV Ingestion API locally..."
# If python doesn't have the requests package globally on host, we can also run the verification script inside the backend container!
docker exec paths_backend python scripts/verify_ingestion.py

Write-Host ""
Write-Host "=========================================="
Write-Host "Setup and verification fully complete!"
Write-Host "=========================================="
