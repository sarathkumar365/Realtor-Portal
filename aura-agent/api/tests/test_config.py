from app.config import Settings


def test_a_fresh_deploy_runs_no_jobs_and_files_only_to_the_test_folder():
    settings = Settings(_env_file=None)
    assert settings.unbrander_enabled is False
    assert settings.unbrander_dry_run is True


def test_the_service_account_key_has_no_default():
    assert Settings(_env_file=None).google_service_account_json == ""
