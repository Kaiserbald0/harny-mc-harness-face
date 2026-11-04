import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import logging
import os

from harness import git
from harness.get_plans import get_plans
from harness.implement import implement
from harness.review import review
from harness.role import PLANNER_CONSERVATIVE, PLANNER_EXPLORATIVE, IMPLEMENTER, REVIEWER, IMPLEMENTER_FIX
from harness.run_revision import run_revision
from harness.selector import selector
from harness.verify import verify
from harness.tool import sandbox_root
from harness.memory import load_skills, format_for_prompt
from harness.trace import log_step, RunStep, StepStatus

SPEC = """
Build a simple API using golang. The APi is an health check for the service so it should respond to GET /health
"""

MAX_FIX_CYCLES = 2

def main():
    load_dotenv()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    client = OpenAI(
        base_url=os.getenv("LLM_API_ENDPOINT"),
        api_key=os.getenv("LLM_API_KEY"),
    )

    run_id = str(uuid.uuid4())

    sandbox = sandbox_root()
    git.ensure_repo(sandbox)
    branch = git.create_branch(sandbox, f"harny/{run_id[:8]}")

    skills = load_skills(scope="global")
    skills_block = format_for_prompt(skills)
    if skills:
        spec_with_skills = f"{skills_block}\n\n{SPEC}"
        log_step(
            run_id=run_id, step=RunStep.RETRIEVAL, turn=0, role="librarian",
            model="", temperature=0.0,
            input_summary=SPEC[:500],
            output=f"injected {len(skills)} skills: {[s.id for s in skills]}",
            status=StepStatus.OK,
        )
    else:
        spec_with_skills = SPEC


    roles_list = [PLANNER_CONSERVATIVE, PLANNER_EXPLORATIVE]
    plans = get_plans(spec=spec_with_skills, roles=roles_list, run_id=run_id, client=client)
    print(f"\n=== {len(plans)} plans ===")
    selected_plan, rational, selected_index = selector(
        plans=plans,
        spec=spec_with_skills,
        run_id=run_id,
        client=client,
        model=os.getenv("SELECTOR_MODEL")
    )
    print(f"\n=== {len(plans)} plans ===")
    print(f"\n=== selected plan: \n {selected_plan} ===")
    print(f"\n=== rational: \n{rational} ===")
    chosen_role = roles_list[selected_index]
    revised_plan = run_revision(
        plan=selected_plan,
        role=chosen_role,
        spec=spec_with_skills,
        run_id=run_id,
        client=client
    )
    print(f"\n=== revised plan: \n {revised_plan} ===")

    result = implement(
        plan=revised_plan,
        findings=[],
        client=client,
        run_id=run_id,
        role=IMPLEMENTER,
        max_turns=10,
    )
    diff, changed = "", []
    if not result.finished:
        print(f"WARN: implementer did not finish after {result.turns_used} turns")
        print(f"      files written so far: {result.files_written}")
    else:
        print(f"implementer finished in {result.turns_used} turns")
        print(f"files: {result.files_written}")
        print(f"final text: {result.final_text[:200]}")
        if result.files_written:
            commit = git.commit_all(
                sandbox,
                message=f"ai: {SPEC.strip().splitlines()[0][:72]} (run {run_id[:8]})",
            )
            diff = git.diff_against(sandbox, base="main")
            changed = git.changed_files(sandbox, base="main")
            artifact_dir = Path("artifacts") / run_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "diff.patch").write_text(diff)

            log_step(
                run_id=run_id, step=RunStep.GIT, turn=0, role="harness",
                model="", temperature=0.0, input_summary=branch,
                output=f"commit={commit.sha[:8]} files={len(changed)} diff_bytes={len(diff)} artifact={artifact_dir}/diff.patch",
                status=StepStatus.OK if commit.committed else StepStatus.EMPTY,
            )

    for cycle in range(MAX_FIX_CYCLES):
        verify_result = verify(sandbox, run_id=run_id, language="go")
        findings = review(
            spec=spec_with_skills, plan=revised_plan, path=sandbox,
            verify_result=verify_result, role=REVIEWER,
            run_id=run_id, files_written=result.files_written, client=client,
            diff=diff,
        )
        blockers = [f for f in findings if f["severity"] in ("blocker", "major")]
        if not blockers and verify_result.passed:
            break
        if cycle == MAX_FIX_CYCLES - 1:
            print(f"WARN: still {len(blockers)} findings; proceeding anyway")
            break
        result = implement(
            plan=revised_plan,
            findings=findings,
            client=client,
            run_id=run_id,
            role=IMPLEMENTER_FIX,
            max_turns=10,
        )
        if not result.finished:
            print(f"WARN: implementer did not finish after {result.turns_used} turns")
            print(f"      files written so far: {result.files_written}")
        else:
            print(f"implementer fix cycle {cycle} finished in {result.turns_used} turns")
            print(f"files: {result.files_written}")
            print(f"final text: {result.final_text[:200]}")
            if result.files_written:
                commit = git.commit_all(
                    sandbox,
                    message=f"ai: fix cycle {cycle} — {len(blockers)} findings",
                )
                diff = git.diff_against(sandbox, base="main")
                changed = git.changed_files(sandbox, base="main")
                log_step(
                    run_id=run_id, step=RunStep.GIT, turn=0, role="harness",
                    model="", temperature=0.0, input_summary=branch,
                    output=f"commit={commit.sha[:8]} files={len(changed)} diff_bytes={len(diff)}",
                    status=StepStatus.OK if commit.committed else StepStatus.EMPTY,
                )

if __name__ == "__main__":
    main()
