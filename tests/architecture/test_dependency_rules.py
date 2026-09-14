"""
Enforce the Clean Architecture dependency rules.

The project's identity document (docs/00-project-identity.md section 6)
declares the rules these tests check. The rules, restated here so that the
tests can be read on their own:

    domain        must not import Django, DRF, drf-spectacular, the
                  Elasticsearch client, or any other layer of this app.

    application   same as domain, except that it may import from domain.
                  It coordinates use cases and depends on domain ports.

    presentation  may use Django / DRF / drf-spectacular, and may import
                  from application and domain. It must not import the
                  Elasticsearch client or the app's own infrastructure
                  layer, with exactly one sanctioned exception: the
                  composition root.

    infrastructure
                  is the only layer that may import the Elasticsearch
                  client. It must not import the application or
                  presentation layers, because it serves them, not the
                  other way around.

Two distinct "infrastructure" concepts exist in this repository and must
not be conflated:

    * The top-level ``infrastructure`` package is the managed Elasticsearch
      client lifecycle established in Phase 1.4. It behaves like a
      framework for the domain, application, and presentation layers (they
      must not reach around and grab a client), but it is a legitimate
      dependency of the app's infrastructure layer, which exists to adapt
      it.

    * The app-local ``apps.search.infrastructure`` package is the
      infrastructure layer of the search app. Only the composition root
      may import it from outside.

Enforcement is done by walking the source tree with ``ast``. Enforcement
at the import level is what makes the rules real: a rule that is only
documented erodes one pragmatic import at a time.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "apps" / "search"

# Frameworks, transport libraries, and the Elasticsearch client. Forbidden
# to any layer that does not explicitly opt in to them.
FRAMEWORK_PACKAGES = {
    "django",
    "rest_framework",
    "drf_spectacular",
    "elasticsearch",
    "elastic_transport",
}

# The top-level managed Elasticsearch client package (Phase 1.4). Distinct
# from the app-local "apps.search.infrastructure" layer.
TOP_LEVEL_CLIENT_PACKAGE = "infrastructure"

# Per-layer rules. Each layer declares:
#
#   forbidden_prefixes         internal app paths the layer must not import
#   allow_framework_packages   may import Django / DRF / drf-spectacular / ES client
#   allow_top_level_client     may import the top-level ``infrastructure`` package
LAYER_RULES: dict[str, dict[str, object]] = {
    "domain": {
        "forbidden_prefixes": [
            "apps.search.application",
            "apps.search.presentation",
            "apps.search.infrastructure",
        ],
        "allow_framework_packages": False,
        "allow_top_level_client": False,
    },
    "application": {
        "forbidden_prefixes": [
            "apps.search.presentation",
            "apps.search.infrastructure",
        ],
        "allow_framework_packages": False,
        "allow_top_level_client": False,
    },
    "presentation": {
        "forbidden_prefixes": [
            "apps.search.infrastructure",
        ],
        "allow_framework_packages": True,
        # Presentation must talk through use cases, not grab a client.
        "allow_top_level_client": False,
    },
    "infrastructure": {
        "forbidden_prefixes": [
            "apps.search.application",
            "apps.search.presentation",
        ],
        "allow_framework_packages": True,
        # The infrastructure layer exists precisely to adapt the managed
        # Elasticsearch client, so this import is expected here.
        "allow_top_level_client": True,
    },
}

# The composition root is the single sanctioned exception in the
# presentation layer: its purpose is to instantiate concrete
# infrastructure adapters and inject them into application use cases.
COMPOSITION_ROOT_RELATIVE = "apps/search/presentation/composition.py"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------
def _python_files(layer_dir: Path) -> list[Path]:
    return sorted(p for p in layer_dir.rglob("*.py") if p.is_file())


def _collect_imports(source_path: Path) -> set[str]:
    """Return every module path imported by ``source_path`` (dotted form)."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # Relative imports (level > 0) resolve inside the same package;
            # they cannot escape the layer they were written in and are
            # therefore not subject to cross-layer rules.
            imported.add(node.module)
    return imported


def _relative(source_path: Path) -> str:
    return source_path.relative_to(REPO_ROOT).as_posix()


def _is_sanctioned_composition_exception(layer: str, relative: str) -> bool:
    """
    True if a file is the composition root and the layer is presentation.

    The composition root is the one place in the codebase whose
    entire purpose is to construct concrete adapters and inject
    them into use cases. To do that, it must import concrete
    packages: the top-level Elasticsearch client package and the
    app-local infrastructure layer. Every other file in the
    presentation layer must go through a use case that was
    constructed elsewhere.

    This helper makes the exception explicit and consults it in
    every branch of the rule loop below. A silent allowance in one
    branch and a violation in another would be a bug.
    """
    return layer == "presentation" and relative == COMPOSITION_ROOT_RELATIVE


def _violations_in_layer(layer: str) -> list[tuple[str, str]]:
    """Return a list of (file, forbidden_import) violations in a layer."""
    rules = LAYER_RULES[layer]
    forbidden_prefixes = rules["forbidden_prefixes"]  # type: ignore[assignment]
    allow_frameworks = bool(rules["allow_framework_packages"])
    allow_top_level_client = bool(rules["allow_top_level_client"])

    layer_dir = APP_ROOT / layer
    violations: list[tuple[str, str]] = []

    for source_file in _python_files(layer_dir):
        relative = _relative(source_file)
        is_composition = _is_sanctioned_composition_exception(layer, relative)
        imports = _collect_imports(source_file)

        for imported in imports:
            top_level = imported.split(".")[0]

            if not allow_frameworks and top_level in FRAMEWORK_PACKAGES:
                if is_composition:
                    continue
                violations.append((relative, imported))
                continue

            if not allow_top_level_client and top_level == TOP_LEVEL_CLIENT_PACKAGE:
                # The composition root must import the top-level
                # client package to obtain a client and to read the
                # index alias. Every other presentation file must
                # not.
                if is_composition:
                    continue
                violations.append((relative, imported))
                continue

            for prefix in forbidden_prefixes:
                if imported == prefix or imported.startswith(prefix + "."):
                    if is_composition:
                        break
                    violations.append((relative, imported))
                    break

    return violations


# ---------------------------------------------------------------------------
# Self-tests: the AST walker must actually find imports
# ---------------------------------------------------------------------------
def test_ast_walker_detects_a_known_import() -> None:
    """Guard against a broken walker silently passing every other rule."""
    known_file = APP_ROOT / "domain" / "search_query.py"
    imports = _collect_imports(known_file)
    assert "apps.search.domain.exceptions" in imports
    assert "apps.search.domain.pagination" in imports


def test_ast_walker_sees_no_imports_in_an_empty_module(tmp_path: Path) -> None:
    empty = tmp_path / "empty.py"
    empty.write_text("", encoding="utf-8")
    assert _collect_imports(empty) == set()


# ---------------------------------------------------------------------------
# Per-layer rule tests
# ---------------------------------------------------------------------------
def test_domain_layer_is_framework_free_and_layer_isolated() -> None:
    violations = _violations_in_layer("domain")
    assert violations == [], f"domain layer violations: {violations}"


def test_application_layer_is_framework_free_and_layer_isolated() -> None:
    violations = _violations_in_layer("application")
    assert violations == [], f"application layer violations: {violations}"


def test_presentation_layer_does_not_import_infrastructure_except_composition() -> None:
    violations = _violations_in_layer("presentation")
    assert violations == [], f"presentation layer violations: {violations}"


def test_infrastructure_layer_does_not_import_upward() -> None:
    violations = _violations_in_layer("infrastructure")
    assert violations == [], f"infrastructure layer violations: {violations}"


def test_composition_root_exists_and_is_the_only_exception() -> None:
    """Document the exception explicitly so removing it fails loudly."""
    composition = REPO_ROOT / COMPOSITION_ROOT_RELATIVE
    assert composition.exists(), (
        "the composition root is the sole sanctioned exception to the "
        "presentation -> infrastructure rule; if it moved, update the test"
    )
