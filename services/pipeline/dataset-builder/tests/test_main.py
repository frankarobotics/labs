import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import main
from models.dataset_build_request import DatasetBuildRequest


def _request(output_dir: Path) -> DatasetBuildRequest:
    return DatasetBuildRequest(
        mcap_files=(Path("episode.mcap"),),
        output_dir=output_dir,
        target_format="lerobot",
        dataset_name=output_dir.name,
        policy_contract_path=Path("contract.yaml"),
        policy_type="gr00t",
    )


def _writing_build(after_write: Callable[[], None] = lambda: None) -> Callable[[DatasetBuildRequest], dict[str, Any]]:
    def build(request: DatasetBuildRequest) -> dict[str, Any]:
        # mirrors LeRobot claiming its root with exist_ok=False
        request.output_dir.mkdir()
        info = request.output_dir / "meta" / "info.json"
        info.parent.mkdir()
        info.write_text("{}")
        after_write()
        return {"episode_metadata": [], "metadata_files": {"info": info}, "dataset_dir": request.output_dir}

    return build


def _claim_by_other_process(output_dir: Path) -> None:
    output_dir.mkdir()
    (output_dir / "theirs").write_text("keep")


def test_a_successful_build_lands_at_the_output_with_no_staging_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "dataset"
    monkeypatch.setattr(main, "build_dataset", _writing_build())

    result = main._build_staged(_request(output_dir))

    assert (output_dir / "meta" / "info.json").is_file()
    assert result["dataset_dir"] == output_dir
    assert result["metadata_files"] == {"info": output_dir / "meta" / "info.json"}
    assert [path.name for path in tmp_path.iterdir()] == ["dataset"]


def test_an_empty_output_directory_is_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "dataset"
    output_dir.mkdir()
    monkeypatch.setattr(main, "build_dataset", _writing_build())

    main._build_staged(_request(output_dir))

    assert (output_dir / "meta" / "info.json").is_file()
    assert [path.name for path in output_dir.iterdir()] == ["meta"]


def test_an_interrupted_build_removes_its_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "dataset"

    def interrupt() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(main, "build_dataset", _writing_build(interrupt))

    with pytest.raises(KeyboardInterrupt):
        main._build_staged(_request(output_dir))

    assert list(tmp_path.iterdir()) == []


def test_a_failed_build_removes_only_its_own_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "dataset"

    def fail() -> None:
        _claim_by_other_process(output_dir)
        raise ValueError("build failed")

    monkeypatch.setattr(main, "build_dataset", _writing_build(fail))

    with pytest.raises(ValueError, match="build failed"):
        main._build_staged(_request(output_dir))

    assert (output_dir / "theirs").read_text() == "keep"
    assert [path.name for path in tmp_path.iterdir()] == ["dataset"]


def test_an_output_claimed_during_the_build_is_left_intact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "dataset"
    monkeypatch.setattr(main, "build_dataset", _writing_build(lambda: _claim_by_other_process(output_dir)))

    with pytest.raises(RuntimeError, match="could not be moved"):
        main._build_staged(_request(output_dir))

    assert [path.name for path in output_dir.iterdir()] == ["theirs"]
    (staged_root,) = (path for path in tmp_path.iterdir() if path.name.endswith(".partial"))
    assert (staged_root / "dataset" / "meta" / "info.json").is_file()


@pytest.mark.parametrize("value", ["0", "-20", "7.5", "nan", "thirty"])
def test_fps_that_is_not_a_positive_whole_number_is_rejected(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="positive whole number"):
        main._positive_int_type(value)


def test_fps_parses_a_positive_whole_number() -> None:
    assert main._positive_int_type("30") == 30
