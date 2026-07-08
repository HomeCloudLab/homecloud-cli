from homecloud_core.so_paths import (
    encode_object_key_path,
    so_object_paths,
    sync_relative_local_path,
)


def test_encode_object_key_path_spaces() -> None:
    assert encode_object_key_path("watch/spider noir/1/file.mkv") == (
        "watch/spider%20noir/1/file.mkv"
    )


def test_so_object_paths_sign_vs_url() -> None:
    account_id = "acc-1"
    sign_path, url_path = so_object_paths(
        account_id,
        "my-bucket",
        "watch/spider noir/1/file.mkv",
    )
    assert sign_path == "/acc-1/my-bucket/objects/watch/spider noir/1/file.mkv"
    assert url_path == "/acc-1/my-bucket/objects/watch/spider%20noir/1/file.mkv"


def test_sync_relative_local_path_directory_prefix() -> None:
    assert sync_relative_local_path(
        "watch/spider noir/1/file.mkv",
        "watch/spider noir/1",
    ) == "file.mkv"


def test_sync_relative_local_path_exact_file() -> None:
    key = "watch/spider noir/1/file.mkv"
    assert sync_relative_local_path(key, key) == "file.mkv"
