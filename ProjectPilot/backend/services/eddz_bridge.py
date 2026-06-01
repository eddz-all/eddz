import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
EDDZ_ROOT = WORKSPACE_ROOT / "eddz"
ENGINE_ROOT = WORKSPACE_ROOT / "engine" / "engine"


def _select_projectpilot_root() -> Path | None:
    if EDDZ_ROOT.exists():
        return EDDZ_ROOT
    if ENGINE_ROOT.exists():
        return ENGINE_ROOT
    return None


PROJECTPILOT_ROOT = _select_projectpilot_root()
INTEGRATION_SOURCE = None
IMPORT_ERROR = None

if PROJECTPILOT_ROOT is not None:
    if str(PROJECTPILOT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECTPILOT_ROOT))
    INTEGRATION_SOURCE = PROJECTPILOT_ROOT.name

try:
    from projectpilot.executor.remote import (
        check_connection as bridge_check_connection,
    )
    from projectpilot.executor.remote import (
        detect_remote_environment as bridge_detect_remote_environment,
    )
    from projectpilot.executor.remote import (
        detect_remote_git_status as bridge_detect_remote_git_status,
    )
    from projectpilot.executor.remote import (
        run_remote_script as bridge_run_remote_script,
    )
    from projectpilot.integration.member_b import (
        detect_local_environment as bridge_detect_local_environment,
    )
    from projectpilot.integration.member_b import (
        detect_local_git_status as bridge_detect_local_git_status,
    )
    from projectpilot.integration.smart_git import (
        analyze_repository as bridge_analyze_repository,
    )
except ImportError as error:
    IMPORT_ERROR = error
    bridge_check_connection = None
    bridge_detect_remote_environment = None
    bridge_detect_remote_git_status = None
    bridge_run_remote_script = None
    bridge_detect_local_environment = None
    bridge_detect_local_git_status = None
    bridge_analyze_repository = None


def integration_runtime():
    return {
        "available": IMPORT_ERROR is None and PROJECTPILOT_ROOT is not None,
        "source": INTEGRATION_SOURCE,
        "root": str(PROJECTPILOT_ROOT) if PROJECTPILOT_ROOT is not None else None,
        "import_error": str(IMPORT_ERROR) if IMPORT_ERROR is not None else None,
    }
