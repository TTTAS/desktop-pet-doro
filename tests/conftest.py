"""Pytest configuration and shared fixtures."""

from pathlib import Path
from typing import Optional
from unittest.mock import Mock

import pytest

from doro_app.state_models import State, MoveState, TransitionState
from doro_app.state_repository import (
    StateRepository,
    MoveStateRepository,
    GifRepository,
    TransitionStateRepository,
)
from doro_app.state_service import StateService


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for tests."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture
def temp_state_file(temp_data_dir: Path) -> Path:
    """Create a temporary state file path."""
    return temp_data_dir / "states.json"


@pytest.fixture
def temp_move_state_file(temp_data_dir: Path) -> Path:
    """Create a temporary move state file path."""
    return temp_data_dir / "move_states.json"


@pytest.fixture
def temp_transition_file(temp_data_dir: Path) -> Path:
    """Create a temporary transition file path."""
    return temp_data_dir / "transitions.json"


@pytest.fixture
def temp_state_list_file(temp_data_dir: Path) -> Path:
    """Create a temporary state list file path."""
    return temp_data_dir / "state_list.txt"


@pytest.fixture
def temp_gif_storage(temp_data_dir: Path) -> Path:
    """Create a temporary GIF storage directory."""
    storage = temp_data_dir / "STORAGE"
    storage.mkdir(parents=True, exist_ok=True)
    return storage


@pytest.fixture
def mock_state_repo() -> Mock:
    """Create a mock StateRepository."""
    repo = Mock(spec=StateRepository)
    repo.load_all.return_value = {}
    repo.save_all.return_value = True
    return repo


@pytest.fixture
def mock_move_repo() -> Mock:
    """Create a mock MoveStateRepository."""
    repo = Mock(spec=MoveStateRepository)
    repo.load_all.return_value = {}
    repo.save_all.return_value = True
    return repo


@pytest.fixture
def mock_gif_repo() -> Mock:
    """Create a mock GifRepository."""
    repo = Mock(spec=GifRepository)
    repo.get_path.return_value = None
    repo.store_gif.return_value = "test_gif_id"
    repo.delete.return_value = True
    repo.get_state_storage_path.return_value = Path("/fake/path")
    repo.get_move_storage_path.return_value = Path("/fake/path")
    repo.sanitize_filename.side_effect = lambda x: x.replace(" ", "_")
    return repo


@pytest.fixture
def mock_transition_repo() -> Mock:
    """Create a mock TransitionStateRepository."""
    repo = Mock(spec=TransitionStateRepository)
    repo.load_all.return_value = {}
    repo.save_all.return_value = True
    return repo


@pytest.fixture
def state_service_with_mocks(
    mock_state_repo: Mock,
    mock_move_repo: Mock,
    mock_gif_repo: Mock,
    temp_state_list_file: Path,
    mock_transition_repo: Mock,
) -> StateService:
    """
    Create a StateService instance with mocked dependencies.

    This is the primary fixture for testing StateService in isolation.
    """
    service = StateService(
        state_repo=mock_state_repo,
        move_repo=mock_move_repo,
        gif_repo=mock_gif_repo,
        state_list_path=temp_state_list_file,
        transition_repo=mock_transition_repo,
    )
    return service


@pytest.fixture
def real_state_service(
    temp_state_file: Path,
    temp_move_state_file: Path,
    temp_gif_storage: Path,
    temp_state_list_file: Path,
    temp_transition_file: Path,
) -> StateService:
    """
    Create a StateService instance with real repositories.

    Use this for integration tests that need actual file I/O.
    """
    state_repo = StateRepository(temp_state_file)
    move_repo = MoveStateRepository(temp_move_state_file)
    gif_repo = GifRepository(temp_gif_storage)
    transition_repo = TransitionStateRepository(temp_transition_file)

    service = StateService(
        state_repo=state_repo,
        move_repo=move_repo,
        gif_repo=gif_repo,
        state_list_path=temp_state_list_file,
        transition_repo=transition_repo,
    )
    return service


@pytest.fixture
def sample_state() -> State:
    """Create a sample State for testing."""
    return State(
        key="test_state",
        label="Test State",
        name_tag="test_doro",
        gif_id="test_gif_123",
    )


@pytest.fixture
def sample_move_state() -> MoveState:
    """Create a sample MoveState for testing."""
    return MoveState(
        key="walk_right",
        state_key="walking",
        direction="right",
        default_distance=100.0,
        default_speed="med",
    )


@pytest.fixture
def sample_transition() -> TransitionState:
    """Create a sample TransitionState for testing."""
    return TransitionState(
        key="idle_to_happy",
        from_state="idle",
        to_state="happy",
        gif_id="transition_gif",
    )
