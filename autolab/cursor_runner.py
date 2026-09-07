import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

PROMPT_FILE = (
    ROOT
    / "autolab"
    / "prompts"
    / "MASTER_AUTONOMOUS_LAB.md"
)

START_PROMPT_FILE = (
    ROOT
    / "autolab"
    / "prompts"
    / "START_6H_LAB.md"
)


def run_cursor_agent(
    prompt: str,
    timeout: int = 3600,
):

    command = [
        "agent",
        "-p",
        prompt,
        "--force",
        "--output-format",
        "text",
    ]

    print(
        "Starting Cursor Agent...",
        flush=True,
    )

    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    output = []

    assert process.stdout is not None

    for line in process.stdout:

        print(
            line,
            end="",
            flush=True,
        )

        output.append(line)

    return_code = process.wait(
        timeout=timeout
    )

    return {
        "return_code": return_code,
        "output": "".join(output),
    }


def main():

    # Prefer the full start brief; fall back to master prompt.
    path = START_PROMPT_FILE if START_PROMPT_FILE.exists() else PROMPT_FILE
    prompt = path.read_text(encoding="utf-8")

    result = run_cursor_agent(prompt)

    print(
        json.dumps(
            {
                "success": result["return_code"] == 0,
                "return_code": result["return_code"],
                "prompt_file": str(path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
