import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))


class _FakeTaskResult:
    def __rshift__(self, other):
        return other


class _FakeTaskCallable:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args, **kwargs):
        return _FakeTaskResult()

    def expand(self, **kwargs):
        return _FakeTaskResult()


def _fake_task(*decorator_args, **decorator_kwargs):
    if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
        return _FakeTaskCallable(decorator_args[0])

    def decorator(fn):
        return _FakeTaskCallable(fn)

    return decorator


def _fake_dag(*args, **kwargs):
    def decorator(fn):
        return fn

    return decorator


class _FakeParam:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def _install_module(name: str, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


_install_module("airflow")
_install_module("airflow.decorators", dag=_fake_dag, task=_fake_task)
_install_module("airflow.models")
_install_module("airflow.models.param", Param=_FakeParam)

_install_module("fitz")

shared_module = _install_module("shared")
shared_module.__path__ = []
_install_module("shared.db", SessionLocal=MagicMock())
shared_arxiv_module = _install_module("shared.arxiv")
shared_arxiv_module.__path__ = []
_install_module("shared.arxiv.client", fetch_pdf_for_processing=MagicMock())

papers_module = _install_module("papers")
papers_module.__path__ = []
_install_module("papers.models", Paper=MagicMock())
_install_module("papers.client", save_paper=MagicMock(), create_paper_slug=MagicMock())
papers_db_module = _install_module("papers.db")
papers_db_module.__path__ = []
_install_module("papers.db.models", PaperRecord=type("PaperRecord", (), {}))

paperprocessor_module = _install_module("paperprocessor")
paperprocessor_module.__path__ = []
_install_module("paperprocessor.client", process_paper_pdf=MagicMock())
_install_module("paperprocessor.models", ProcessedDocument=type("ProcessedDocument", (), {}))

users_module = _install_module("users")
users_module.__path__ = []
_install_module("users.client", set_requests_processed=MagicMock())


from dags.paper_processing_worker_dag import _claim_next_job, _normalize_optional_date_param


def test_normalize_optional_date_param_handles_airflow_null_variants():
    assert _normalize_optional_date_param(None) is None
    assert _normalize_optional_date_param("") is None
    assert _normalize_optional_date_param("   ") is None
    assert _normalize_optional_date_param("None") is None
    assert _normalize_optional_date_param("null") is None
    assert _normalize_optional_date_param(" 2026-04-10 ") == "2026-04-10"


def test_claim_next_job_ignores_stringified_null_date_filters():
    session = MagicMock()
    session.execute.return_value.first.return_value = None

    result = _claim_next_job(session, date_from="None", date_to="null")

    assert result is None
    statement, params = session.execute.call_args.args
    assert "created_at >=" not in str(statement)
    assert "CAST(:date_to AS date)" not in str(statement)
    assert params == {}
