from __future__ import annotations

import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "Dockerfile",
    "render.yaml",
    ".env.example",
    "requirements.txt",
    "requirements-dev.txt",
    "database/schema.sql",
    "README.md",
    "bot/main.py",
)


def check_required_files() -> list[str]:
    problems = []

    for relative_path in REQUIRED_FILES:
        if not (PROJECT_ROOT / relative_path).exists():
            problems.append(
                f"Fichier manquant : {relative_path}"
            )

    return problems


def check_python_syntax() -> list[str]:
    problems = []

    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")

        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as error:
            relative = path.relative_to(PROJECT_ROOT)
            problems.append(
                f"Erreur de syntaxe dans {relative} : {error}"
            )

    return problems


def check_no_real_secrets() -> list[str]:
    problems = []

    env_path = PROJECT_ROOT / ".env"

    if env_path.exists():
        problems.append(
            ".env est présent dans le dossier généré : "
            "ne jamais l'envoyer sur GitHub."
        )

    return problems


def main() -> int:
    problems: list[str] = []
    problems += check_required_files()
    problems += check_python_syntax()
    problems += check_no_real_secrets()

    if problems:
        print("Problèmes détectés :\n")

        for problem in problems:
            print(f"  - {problem}")

        print(
            f"\n{len(problems)} problème(s). "
            "Corrige-les avant de déployer."
        )

        return 1

    print("Vérification réussie : aucun problème détecté.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
