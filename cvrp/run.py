import subprocess
import sys
from pathlib import Path
import time


base_dir = Path(__file__).resolve().parent

programs = [
    base_dir / "mtz.py",
    base_dir / "dl.py"
]

results = []

for program in programs:
    print()
    print("=" * 60)
    print(f"Running {program.name}")
    print("=" * 60)

    start_time = time.perf_counter()

    completed = subprocess.run(
        [sys.executable, str(program)],
        cwd=base_dir,
        check=False
    )

    elapsed_time = time.perf_counter() - start_time

    results.append({
        "name": program.name,
        "returncode": completed.returncode,
        "elapsed_time": elapsed_time
    })

    print()
    print(
        f"{program.name} finished: "
        f"returncode={completed.returncode}, "
        f"elapsed_time={elapsed_time:.3f} sec"
    )

print()
print("=" * 60)
print("Execution summary")
print("=" * 60)

for result in results:
    status = (
        "SUCCESS"
        if result["returncode"] == 0
        else "FAILED"
    )

    print(
        f"{result['name']}: "
        f"{status}, "
        f"elapsed_time={result['elapsed_time']:.3f} sec"
    )

if any(result["returncode"] != 0 for result in results):
    sys.exit(1)