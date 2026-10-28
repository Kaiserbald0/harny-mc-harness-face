import uuid

from dotenv import load_dotenv
from openai import OpenAI
import logging
import os

from harness.critic import critique

SPEC = """
Build a simple API using golang. The APi is an health check for the service so it should respond to GET /health
"""

def main():
    load_dotenv()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )
    run_id = str(uuid.uuid4())
    conservative = """1. Initialize Go module with `go mod init healthcheck`
2. Create main.go containing package main, import net/http and encoding/json, define a HealthHandler that writes JSON `{"status":"ok"}` with HTTP status 200, register it on the `/health` path, and start the server listening on `:8080`
3. Run the API with `go run main.go` to start the health check endpoint"""
    explorative = """1. Create a new Go module by running go mod init example.com/healthcheck.
2. Add the net/http package import to main.go.
3. Implement a HealthHandler function in main.go that accepts an http.ResponseWriter and http.Request.
4. In HealthHandler, return http.StatusMethodNotAllowed for any request method other than GET.
5. In HealthHandler, set the response Content-Type to application/json and write a 200 status code.
6. In HealthHandler, write a JSON response body of {"status":"ok"} to the writer.
7. Register the HealthHandler on the /health route using http.HandleFunc.
8. Start an HTTP server on port 8080 listening on :8080.
9. Handle the error returned by http.ListenAndServe by logging it.
10. Add a Go test file for the health check endpoint.
11. Write a test that performs a GET request to /health and expects a 200 status code.
12. Write a test that verifies the GET /health response body contains {"status":"ok"}.
13. Write a test that performs a POST request to /health and expects a 405 status code.
14. Run go test ./... and go build ./... to verify the implementation."""  # 11 steps

    print("CONSERVATIVE:", critique(conservative, SPEC, run_id, client))
    print("EXPLORATIVE:", critique(explorative, SPEC, run_id, client))


if __name__ == "__main__":
    main()
