"""
Build Commands
==============

CLI commands for building specs and handling the main build flow.
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure parent directory is in path for imports (before other imports)
_PARENT_DIR = Path(__file__).parent.parent
if str(_PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(_PARENT_DIR))

# Import only what we need at module level
# Heavy imports are lazy-loaded in functions to avoid import errors
from progress import print_paused_banner
from review import ReviewState
from ui import (
    BuildState,
    Icons,
    MenuOption,
    StatusManager,
    bold,
    box,
    highlight,
    icon,
    muted,
    print_status,
    select_menu,
    success,
    warning,
)
from workspace import (
    WorkspaceMode,
    check_existing_build,
    choose_workspace,
    finalize_workspace,
    get_existing_build_worktree,
    handle_workspace_choice,
    setup_workspace,
)

from .input_handlers import (
    read_from_file,
    read_multiline_input,
)

# Docker isolation adapter
from core.isolation_adapter import (
    should_use_docker_isolation,
    get_isolation_strategy,
)


def handle_build_command(
    project_dir: Path,
    spec_dir: Path,
    model: str,
    max_iterations: int | None,
    verbose: bool,
    force_isolated: bool,
    force_direct: bool,
    auto_continue: bool,
    skip_qa: bool,
    force_bypass_approval: bool,
    base_branch: str | None = None,
) -> None:
    """
    Handle the main build command.

    Args:
        project_dir: Project root directory
        spec_dir: Spec directory path
        model: Model to use (used as default; may be overridden by task_metadata.json)
        max_iterations: Maximum number of iterations (None for unlimited)
        verbose: Enable verbose output
        force_isolated: Force isolated workspace mode
        force_direct: Force direct workspace mode
        auto_continue: Auto-continue mode (non-interactive)
        skip_qa: Skip automatic QA validation
        force_bypass_approval: Force bypass approval check
        base_branch: Base branch for worktree creation (default: current branch)
    """
    # Lazy imports to avoid loading heavy modules
    from agent import run_autonomous_agent, sync_plan_to_source
    from debug import (
        debug,
        debug_info,
        debug_section,
        debug_success,
    )
    from phase_config import get_phase_model
    from qa_loop import run_qa_validation_loop, should_run_qa

    from .utils import print_banner, validate_environment

    # Get the resolved model for the planning phase (first phase of build)
    # This respects task_metadata.json phase configuration from the UI
    planning_model = get_phase_model(spec_dir, "planning", model)
    coding_model = get_phase_model(spec_dir, "coding", model)
    qa_model = get_phase_model(spec_dir, "qa", model)

    print_banner()
    print(f"\nProject directory: {project_dir}")
    print(f"Spec: {spec_dir.name}")
    # Show phase-specific models if they differ
    if planning_model != coding_model or coding_model != qa_model:
        print(
            f"Models: Planning={planning_model.split('-')[1] if '-' in planning_model else planning_model}, "
            f"Coding={coding_model.split('-')[1] if '-' in coding_model else coding_model}, "
            f"QA={qa_model.split('-')[1] if '-' in qa_model else qa_model}"
        )
    else:
        print(f"Model: {planning_model}")

    if max_iterations:
        print(f"Max iterations: {max_iterations}")
    else:
        print("Max iterations: Unlimited (runs until all subtasks complete)")

    print()

    # Validate environment
    if not validate_environment(spec_dir):
        sys.exit(1)

    # Check human review approval
    review_state = ReviewState.load(spec_dir)
    if not review_state.is_approval_valid(spec_dir):
        if force_bypass_approval:
            # User explicitly bypassed approval check
            print()
            print(
                warning(
                    f"{icon(Icons.WARNING)} WARNING: Bypassing approval check with --force"
                )
            )
            print(muted("This spec has not been approved for building."))
            print()
        else:
            print()
            content = [
                bold(f"{icon(Icons.WARNING)} BUILD BLOCKED - REVIEW REQUIRED"),
                "",
                "This spec requires human approval before building.",
            ]

            if review_state.approved and not review_state.is_approval_valid(spec_dir):
                # Spec changed after approval
                content.append("")
                content.append(warning("The spec has been modified since approval."))
                content.append("Please re-review and re-approve.")

            content.extend(
                [
                    "",
                    highlight("To review and approve:"),
                    f"  python auto-claude/review.py --spec-dir {spec_dir}",
                    "",
                    muted("Or use --force to bypass this check (not recommended)."),
                ]
            )
            print(box(content, width=70, style="heavy"))
            print()
            sys.exit(1)
    else:
        debug_success(
            "run.py", "Review approval validated", approved_by=review_state.approved_by
        )

    # Check for existing build
    if get_existing_build_worktree(project_dir, spec_dir.name):
        if auto_continue:
            # Non-interactive mode: auto-continue with existing build
            debug("run.py", "Auto-continue mode: continuing with existing build")
            print("Auto-continue: Resuming existing build...")
        else:
            continue_existing = check_existing_build(project_dir, spec_dir.name)
            if continue_existing:
                # Continue with existing worktree
                pass
            else:
                # User chose to start fresh or merged existing
                pass

    # ============================================================================
    # DOCKER ISOLATION MODE
    # ============================================================================
    # If ISOLATION_METHOD=docker in .env, use Docker containers instead of worktrees
    if should_use_docker_isolation():
        print(f"\n{icon(Icons.DOCKER)} Docker Isolation Mode")
        print("=" * 70)
        print("Using Docker containers for isolated build execution.")
        print("  • Developer container: Implements code")
        print("  • Evaluator container: Reviews quality")
        print("  • QA container: Runs tests")
        print("=" * 70)
        print()

        # Get Docker isolation strategy with configured model
        try:
            isolation = get_isolation_strategy(project_dir, base_branch, model=resolved_model)
        except Exception as e:
            print(f"\n{icon(Icons.ERROR)} Failed to initialize Docker isolation: {e}")
            print("\nTip: Ensure Docker is running and REPO_URL is set.")
            print("Falling back to worktree mode...")
            print()
            # Fall through to worktree mode
        else:
            # Load implementation plan
            from implementation_plan import ImplementationPlan

            plan_path = spec_dir / "implementation_plan.json"
            if not plan_path.exists():
                print(f"\n{icon(Icons.ERROR)} Implementation plan not found: {plan_path}")
                print("Run spec creation first to generate the plan.")
                sys.exit(1)

            # Load and update plan status
            plan_obj = ImplementationPlan.load(plan_path)

            # If plan is in human_review/review state (waiting for approval), start it
            if plan_obj.status == "human_review" and plan_obj.planStatus == "review":
                print(f"{icon(Icons.INFO)} Starting implementation (plan approved)")
                plan_obj.status = "in_progress"
                plan_obj.planStatus = "in_progress"
                plan_obj.save(plan_path)

            # Convert to dict for Docker orchestrator
            plan = plan_obj.to_dict()

            # Setup Docker images (builds if needed)
            print("Setting up Docker environment...")
            isolation.setup()
            print(f"{icon(Icons.SUCCESS)} Docker images ready\n")

            # Status callback for updates
            status_manager = StatusManager(project_dir)

            def on_status_change(spec_name: str, status: str, message: str = ""):
                """Handle status updates from Docker pipeline."""
                print(f"\n[{spec_name}] {status}: {message}")

                # Update status manager
                status_map = {
                    "planning": BuildState.PLANNING,
                    "coding": BuildState.BUILDING,
                    "ai_review": BuildState.BUILDING,
                    "ai_testing": BuildState.QA,
                    "needs_revision": BuildState.BUILDING,
                    "ready_for_review": BuildState.COMPLETE,
                    "failed": BuildState.ERROR,
                }
                build_state = status_map.get(status, BuildState.BUILDING)
                status_manager.update(state=build_state)

            # Run Docker pipeline
            try:
                success = asyncio.run(
                    isolation.run_pipeline(
                        spec_name=spec_dir.name,
                        plan=plan,
                        on_status_change=on_status_change,
                    )
                )

                if success:
                    print("\n" + "=" * 70)
                    print(f"  {icon(Icons.SUCCESS)} DOCKER PIPELINE COMPLETED")
                    print("=" * 70)
                    print("\nAll containers completed successfully.")
                    print("Changes have been pushed to the remote repository.")
                    print(f"\nBranch: auto-claude/{spec_dir.name}")
                    print()
                else:
                    print("\n" + "=" * 70)
                    print(f"  {icon(Icons.ERROR)} DOCKER PIPELINE FAILED")
                    print("=" * 70)
                    print("\nOne or more containers failed.")
                    print(f"Check container logs for details.")
                    print()
                    sys.exit(1)

            except KeyboardInterrupt:
                print("\n\nDocker pipeline interrupted.")
                print(f"Resume: python auto-claude/run.py --spec {spec_dir.name}")
                sys.exit(130)

            # Docker mode complete - skip worktree workflow
            return

    # ============================================================================
    # WORKTREE ISOLATION MODE (Default)
    # ============================================================================
    # Choose workspace (skip for parallel mode - it always uses worktrees)
    working_dir = project_dir
    worktree_manager = None
    source_spec_dir = None  # Track original spec dir for syncing back from worktree

    # Let user choose workspace mode (or auto-select if --auto-continue)
    workspace_mode = choose_workspace(
        project_dir,
        spec_dir.name,
        force_isolated=force_isolated,
        force_direct=force_direct,
        auto_continue=auto_continue,
    )

    if workspace_mode == WorkspaceMode.ISOLATED:
        # Keep reference to original spec directory for syncing progress back
        source_spec_dir = spec_dir

        working_dir, worktree_manager, localized_spec_dir = setup_workspace(
            project_dir,
            spec_dir.name,
            workspace_mode,
            source_spec_dir=spec_dir,
            base_branch=base_branch,
        )
        # Use the localized spec directory (inside worktree) for AI access
        if localized_spec_dir:
            spec_dir = localized_spec_dir

    # Run the autonomous agent
    debug_section("run.py", "Starting Build Execution")
    debug(
        "run.py",
        "Build configuration",
        model=model,
        workspace_mode=str(workspace_mode),
        working_dir=str(working_dir),
        spec_dir=str(spec_dir),
    )

    try:
        debug("run.py", "Starting agent execution")

        asyncio.run(
            run_autonomous_agent(
                project_dir=working_dir,  # Use worktree if isolated
                spec_dir=spec_dir,
                model=model,
                max_iterations=max_iterations,
                verbose=verbose,
                source_spec_dir=source_spec_dir,  # For syncing progress back to main project
            )
        )
        debug_success("run.py", "Agent execution completed")

        # Run QA validation BEFORE finalization (while worktree still exists)
        # QA must sign off before the build is considered complete
        qa_approved = True  # Default to approved if QA is skipped
        if not skip_qa and should_run_qa(spec_dir):
            print("\n" + "=" * 70)
            print("  SUBTASKS COMPLETE - STARTING QA VALIDATION")
            print("=" * 70)
            print("\nAll subtasks completed. Now running QA validation loop...")
            print("This ensures production-quality output before sign-off.\n")

            try:
                qa_approved = asyncio.run(
                    run_qa_validation_loop(
                        project_dir=working_dir,
                        spec_dir=spec_dir,
                        model=model,
                        verbose=verbose,
                    )
                )

                if qa_approved:
                    print("\n" + "=" * 70)
                    print("  ✅ QA VALIDATION PASSED")
                    print("=" * 70)
                    print("\nAll acceptance criteria verified.")
                    print("The implementation is production-ready.\n")
                else:
                    print("\n" + "=" * 70)
                    print("  ⚠️  QA VALIDATION INCOMPLETE")
                    print("=" * 70)
                    print("\nSome issues require manual attention.")
                    print(f"See: {spec_dir / 'qa_report.md'}")
                    print(f"Or:  {spec_dir / 'QA_FIX_REQUEST.md'}")
                    print(
                        f"\nResume QA: python auto-claude/run.py --spec {spec_dir.name} --qa\n"
                    )

                # Sync implementation plan to main project after QA
                # This ensures the main project has the latest status (human_review)
                if sync_plan_to_source(spec_dir, source_spec_dir):
                    debug_info(
                        "run.py", "Implementation plan synced to main project after QA"
                    )
            except KeyboardInterrupt:
                print("\n\nQA validation paused.")
                print(f"Resume: python auto-claude/run.py --spec {spec_dir.name} --qa")
                qa_approved = False

        # Post-build finalization (only for isolated sequential mode)
        # This happens AFTER QA validation so the worktree still exists
        if worktree_manager:
            choice = finalize_workspace(
                project_dir,
                spec_dir.name,
                worktree_manager,
                auto_continue=auto_continue,
            )
            handle_workspace_choice(
                choice, project_dir, spec_dir.name, worktree_manager
            )

    except KeyboardInterrupt:
        _handle_build_interrupt(
            spec_dir=spec_dir,
            project_dir=project_dir,
            worktree_manager=worktree_manager,
            working_dir=working_dir,
            model=model,
            max_iterations=max_iterations,
            verbose=verbose,
        )
    except Exception as e:
        print(f"\nFatal error: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def _handle_build_interrupt(
    spec_dir: Path,
    project_dir: Path,
    worktree_manager,
    working_dir: Path,
    model: str,
    max_iterations: int | None,
    verbose: bool,
) -> None:
    """
    Handle keyboard interrupt during build.

    Args:
        spec_dir: Spec directory path
        project_dir: Project root directory
        worktree_manager: Worktree manager instance (if using isolated mode)
        working_dir: Current working directory
        model: Model being used
        max_iterations: Maximum iterations
        verbose: Verbose mode flag
    """
    from agent import run_autonomous_agent

    # Print paused banner
    print_paused_banner(spec_dir, spec_dir.name, has_worktree=bool(worktree_manager))

    # Update status file
    status_manager = StatusManager(project_dir)
    status_manager.update(state=BuildState.PAUSED)

    # Offer to add human input with enhanced menu
    try:
        options = [
            MenuOption(
                key="type",
                label="Type instructions",
                icon=Icons.EDIT,
                description="Enter guidance for the agent's next session",
            ),
            MenuOption(
                key="paste",
                label="Paste from clipboard",
                icon=Icons.CLIPBOARD,
                description="Paste text you've copied (Cmd+V / Ctrl+Shift+V)",
            ),
            MenuOption(
                key="file",
                label="Read from file",
                icon=Icons.DOCUMENT,
                description="Load instructions from a text file",
            ),
            MenuOption(
                key="skip",
                label="Continue without instructions",
                icon=Icons.SKIP,
                description="Resume the build as-is",
            ),
            MenuOption(
                key="quit",
                label="Quit",
                icon=Icons.DOOR,
                description="Exit without resuming",
            ),
        ]

        choice = select_menu(
            title="What would you like to do?",
            options=options,
            subtitle="Progress saved. You can add instructions for the agent.",
            allow_quit=False,  # We have explicit quit option
        )

        if choice == "quit" or choice is None:
            print()
            print_status("Exiting...", "info")
            status_manager.set_inactive()
            sys.exit(0)

        human_input = ""

        if choice == "file":
            # Read from file
            human_input = read_from_file()
            if human_input is None:
                human_input = ""

        elif choice in ["type", "paste"]:
            human_input = read_multiline_input("Enter/paste your instructions below.")
            if human_input is None:
                print()
                print_status("Exiting without saving instructions...", "warning")
                status_manager.set_inactive()
                sys.exit(0)

        if human_input:
            # Save to HUMAN_INPUT.md
            input_file = spec_dir / "HUMAN_INPUT.md"
            input_file.write_text(human_input)

            content = [
                success(f"{icon(Icons.SUCCESS)} INSTRUCTIONS SAVED"),
                "",
                f"Saved to: {highlight(str(input_file.name))}",
                "",
                muted(
                    "The agent will read and follow these instructions when you resume."
                ),
            ]
            print()
            print(box(content, width=70, style="heavy"))
        elif choice != "skip":
            print()
            print_status("No instructions provided.", "info")

        # If 'skip' was selected, actually resume the build
        if choice == "skip":
            print()
            print_status("Resuming build...", "info")
            status_manager.update(state=BuildState.RUNNING)
            asyncio.run(
                run_autonomous_agent(
                    project_dir=working_dir,
                    spec_dir=spec_dir,
                    model=model,
                    max_iterations=max_iterations,
                    verbose=verbose,
                )
            )
            # Build completed or was interrupted again - exit
            sys.exit(0)

    except KeyboardInterrupt:
        # User pressed Ctrl+C again during input prompt - exit immediately
        print()
        print_status("Exiting...", "warning")
        status_manager = StatusManager(project_dir)
        status_manager.set_inactive()
        sys.exit(0)
    except EOFError:
        # stdin closed
        pass

    # Resume instructions (shown when user provided instructions or chose file/type/paste)
    print()
    content = [
        bold(f"{icon(Icons.PLAY)} TO RESUME"),
        "",
        f"Run: {highlight(f'python auto-claude/run.py --spec {spec_dir.name}')}",
    ]
    if worktree_manager:
        content.append("")
        content.append(muted("Your build is in a separate workspace and is safe."))
    print(box(content, width=70, style="light"))
    print()


def _handle_docker_build(
    project_dir: Path,
    spec_dir: Path,
    model: str,
    base_branch: str | None,
    auto_continue: bool,
    skip_qa: bool,
) -> None:
    """
    Handle build using Docker isolation mode.

    Uses IsolationFactory to create Docker containers for development, evaluation, and QA.

    Args:
        project_dir: Project root directory
        spec_dir: Spec directory path
        model: Model to use
        base_branch: Base branch for branching
        auto_continue: Auto-continue mode
        skip_qa: Skip QA validation
    """
    from core.isolation.factory import IsolationFactory
    import json

    print()
    print("=" * 70)
    print("  DOCKER ISOLATION MODE")
    print("=" * 70)
    print()
    print("Using multi-container pipeline:")
    print("  • Developer container - implements changes")
    print("  • Evaluator container - reviews code quality")
    print("  • QA container - runs automated tests")
    print()

    # Load implementation plan
    plan_file = spec_dir / "implementation_plan.json"
    if not plan_file.exists():
        print(f"Error: Implementation plan not found: {plan_file}")
        print("Run spec creation first: python auto-claude/spec_runner.py")
        sys.exit(1)

    with open(plan_file) as f:
        plan = json.load(f)

    # Create isolation strategy (reads ISOLATION_METHOD from env)
    try:
        strategy = IsolationFactory.create(
            project_dir=project_dir,
            base_branch=base_branch,
            method="docker",  # Explicit docker mode
        )
    except Exception as e:
        print(f"Error creating Docker strategy: {e}")
        print("\nPossible issues:")
        print("  • Docker not installed or not running")
        print("  • Docker images not built")
        print("\nTo build images:")
        print("  cd apps/backend/docker")
        print("  docker build -f Dockerfile.base -t auto-claude-base:latest .")
        print("  docker build -f Dockerfile.developer -t auto-claude-dev:latest .")
        print("  docker build -f Dockerfile.evaluator -t auto-claude-eval:latest .")
        print("  docker build -f Dockerfile.qa -t auto-claude-qa:latest .")
        sys.exit(1)

    # Setup (builds images if needed)
    print("Setting up Docker environment...")
    try:
        strategy.setup()
    except Exception as e:
        print(f"Error setting up Docker: {e}")
        sys.exit(1)

    # Status callback for kanban updates
    status_manager = StatusManager(project_dir)

    def on_status_change(spec_name: str, status: str, message: str = ""):
        """Handle status updates from Docker pipeline."""
        print(f"\n[{spec_name}] {status}: {message}")

        # Update status manager
        status_map = {
            "planning": BuildState.PLANNING,
            "coding": BuildState.BUILDING,
            "ai_review": BuildState.BUILDING,
            "ai_testing": BuildState.QA,
            "needs_revision": BuildState.BUILDING,
            "ready_for_review": BuildState.COMPLETE,
            "failed": BuildState.ERROR,
        }
        build_state = status_map.get(status, BuildState.BUILDING)
        status_manager.update(state=build_state)

    # Run the Docker pipeline
    print()
    print("=" * 70)
    print("  STARTING BUILD PIPELINE")
    print("=" * 70)
    print()

    try:
        success = asyncio.run(
            strategy.run_pipeline(
                spec_name=spec_dir.name,
                plan=plan,
                on_status_change=on_status_change,
            )
        )

        if success:
            print()
            print("=" * 70)
            print("  ✅ BUILD SUCCEEDED")
            print("=" * 70)
            print()
            print("All checks passed! The build is ready for human review.")
            print()

            # Show container status
            container_status = strategy.get_container_status(spec_dir.name)
            print("Container status:")
            for role, state in container_status.items():
                icon_map = {
                    "running": "🟢",
                    "stopped": "🟡",
                    "not_found": "⚪",
                }
                print(f"  {icon_map.get(state, '⚪')} {role}: {state}")
            print()

            # Show merge instructions
            print("To merge the changes:")
            print(f"  python auto-claude/run.py --spec {spec_dir.name} --merge")
            print()
            print("To review changes:")
            print(f"  git diff main...auto-claude/{spec_dir.name}")
            print()
            print("Note: Docker containers will be cleaned up automatically after merge.")
            print()

        else:
            print()
            print("=" * 70)
            print("  ⚠️  BUILD INCOMPLETE")
            print("=" * 70)
            print()
            print("The build did not complete successfully.")
            print("Check the output above for details.")
            print()

            # Show container status
            container_status = strategy.get_container_status(spec_dir.name)
            print("Container status:")
            for role, state in container_status.items():
                icon_map = {
                    "running": "🟢",
                    "stopped": "🟡",
                    "not_found": "⚪",
                }
                print(f"  {icon_map.get(state, '⚪')} {role}: {state}")
            print()

            print("To clean up containers:")
            print(f"  python auto-claude/run.py --spec {spec_dir.name} --discard")
            print()

    except KeyboardInterrupt:
        print()
        print("=" * 70)
        print("  ⏸️  BUILD PAUSED")
        print("=" * 70)
        print()
        print("Build was interrupted.")
        print()
        print("To resume:")
        print(f"  python auto-claude/run.py --spec {spec_dir.name}")
        print()
        print("Note: Docker containers are still running and will be reused on resume.")
        print()

        # Show container status
        container_status = strategy.get_container_status(spec_dir.name)
        print("Container status:")
        for role, state in container_status.items():
            icon_map = {
                "running": "🟢",
                "stopped": "🟡",
                "not_found": "⚪",
            }
            print(f"  {icon_map.get(state, '⚪')} {role}: {state}")
        print()

        sys.exit(0)
    except Exception as e:
        print()
        print("=" * 70)
        print("  ❌ BUILD FAILED")
        print("=" * 70)
        print()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        print()

        # Show container status for debugging
        try:
            container_status = strategy.get_container_status(spec_dir.name)
            print("Container status:")
            for role, state in container_status.items():
                icon_map = {
                    "running": "🟢",
                    "stopped": "🟡",
                    "not_found": "⚪",
                }
                print(f"  {icon_map.get(state, '⚪')} {role}: {state}")
            print()
        except:
            pass

        sys.exit(1)
