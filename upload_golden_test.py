#!/usr/bin/env python3
"""
Script para subir resultados de golden tests a Jira.

Lee el manifest de golden tests, adjunta capturas/diffs y actualiza
la descripción o comentario en la issue de Jira.

Uso:
    # Subir resultado de un test a una issue
    python upload_golden_test.py TGFDEV-123 --test home

    # Subir resultado + cambiar status
    python upload_golden_test.py TGFDEV-123 --test home --status "In Review"

    # Subir solo imágenes custom (sin manifest)
    python upload_golden_test.py TGFDEV-123 --images captura.png diff.png

    # Subir resultado como comentario (no modifica descripción)
    python upload_golden_test.py TGFDEV-123 --test home --as-comment

    # Subir todos los tests que fallaron
    python upload_golden_test.py TGFDEV-123 --failed

    # Subir desde validación personal
    python upload_golden_test.py TGFDEV-123 --test products --validation tincho

    # Listar tests disponibles
    python upload_golden_test.py --list

    # Dry run (ver qué se subiría sin hacerlo)
    python upload_golden_test.py TGFDEV-123 --test home --dry-run

    # Usar mapping de tests a issues
    python upload_golden_test.py --batch --mapping mapping.json

Configuración:
    Variable de entorno GOLDEN_TESTS_PATH o --golden-path para indicar
    la ruta al directorio de golden tests.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from jira_client import JiraClient


# Ruta por defecto al proyecto de golden tests
DEFAULT_GOLDEN_PATH = os.environ.get(
    "GOLDEN_TESTS_PATH",
    os.path.expanduser("~/Documents/Project/prolicht/golden-tests")
)


def load_manifest(golden_path):
    """Carga el manifest de golden tests."""
    manifest_path = os.path.join(golden_path, "tests", "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"Error: No se encontró el manifest en {manifest_path}")
        sys.exit(1)

    with open(manifest_path, "r") as f:
        return json.load(f)


def find_test(manifest, test_id):
    """Busca un test en el manifest por ID."""
    for test in manifest.get("tests", []):
        if test["id"] == test_id:
            return test
    return None


def get_test_images(golden_path, test_id, validation_user=None):
    """
    Obtiene las rutas a las imágenes de un test.

    Returns:
        dict con las rutas a baseline, current y diff
    """
    if validation_user:
        base = os.path.join(golden_path, "validations", validation_user)
        return {
            "current": os.path.join(base, "captures", f"{test_id}.png"),
            "baseline": os.path.join(base, "baselines", f"{test_id}.png"),
            "diff": os.path.join(base, "diffs", f"{test_id}.png"),
        }

    return {
        "baseline": os.path.join(golden_path, "golden-images", "baseline", f"{test_id}.png"),
        "current": os.path.join(golden_path, "golden-images", "current", f"{test_id}.png"),
        "diff": os.path.join(golden_path, "diffs", f"{test_id}.png"),
    }


def format_test_description(test):
    """Genera la descripción del resultado del golden test."""
    result = test.get("lastResult", "N/A")
    similarity = test.get("lastSimilarity", 0)
    last_run = test.get("lastRun", "N/A")
    name = test.get("name", test.get("id", "?"))
    category = test.get("category", "N/A")
    url = test.get("url", "N/A")
    threshold = test.get("threshold", 0.1)
    components = test.get("components", [])
    notes = test.get("notes", "")

    status_emoji = "PASS" if result == "PASS" else "FAIL"
    threshold_pct = (1 - threshold) * 100

    lines = [
        f"Golden Test: {name}",
        f"Resultado: {status_emoji} ({result})",
        f"Similitud: {similarity:.2f}% (threshold: {threshold_pct:.0f}%)",
        f"Categoría: {category}",
        f"URL: {url}",
        f"Última ejecución: {last_run}",
    ]

    if components:
        lines.append(f"Componentes: {', '.join(components)}")

    if notes:
        lines.append(f"Notas: {notes}")

    lines.append("")
    lines.append("Archivos adjuntos: baseline, current screenshot, diff")

    return "\n".join(lines)


def format_test_comment(test, attached_files):
    """Genera el texto del comentario con el resultado."""
    result = test.get("lastResult", "N/A")
    similarity = test.get("lastSimilarity", 0)
    name = test.get("name", test.get("id", "?"))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"[Golden Test] {name} - {result} ({similarity:.2f}%)",
        f"Ejecutado: {test.get('lastRun', timestamp)}",
    ]

    if attached_files:
        lines.append(f"Archivos adjuntos: {', '.join(attached_files)}")

    return "\n".join(lines)


def list_tests(manifest):
    """Lista todos los tests disponibles."""
    tests = manifest.get("tests", [])

    print(f"{'ID':<30} {'RESULTADO':<8} {'SIMILITUD':<12} {'NOMBRE'}")
    print("-" * 90)

    for test in tests:
        test_id = test["id"]
        result = test.get("lastResult", "N/A")[:8]
        similarity = test.get("lastSimilarity", 0)
        name = test.get("name", "-")[:35]
        sim_str = f"{similarity:.1f}%" if similarity else "N/A"

        print(f"{test_id:<30} {result:<8} {sim_str:<12} {name}")

    print(f"\nTotal: {len(tests)} tests")


def upload_test(client, issue_key, test, golden_path, validation_user=None,
                as_comment=False, dry_run=False, status=None):
    """Sube el resultado de un golden test a Jira."""
    test_id = test["id"]
    images = get_test_images(golden_path, test_id, validation_user)

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Subiendo test '{test_id}' a {issue_key}...")

    # Preparar descripción
    description = format_test_description(test)

    if dry_run:
        print(f"  Descripción:\n    {description[:200]}...")
        for img_type, path in images.items():
            exists = "OK" if os.path.exists(path) else "NO ENCONTRADO"
            print(f"  {img_type}: {path} [{exists}]")
        if status:
            print(f"  Status → {status}")
        return True

    # Actualizar descripción o añadir comentario
    attached_files = []

    # Subir imágenes que existan
    for img_type, path in images.items():
        if os.path.exists(path):
            success, result = client.add_attachment(issue_key, path)
            if success:
                filenames = [a.get("filename", "?") for a in result]
                attached_files.extend(filenames)
                print(f"  OK: {img_type} adjuntado ({', '.join(filenames)})")
            else:
                print(f"  Error adjuntando {img_type}: {result}")
        else:
            print(f"  Aviso: {img_type} no encontrado en {path}")

    # Actualizar descripción o comentario
    if as_comment:
        comment_text = format_test_comment(test, attached_files)
        success, result = client.add_comment(issue_key, comment_text)
        if success:
            print(f"  OK: Comentario añadido")
        else:
            print(f"  Error añadiendo comentario: {result}")
    else:
        success, msg = client.update_description(issue_key, description)
        if success:
            print(f"  OK: Descripción actualizada")
        else:
            print(f"  Error actualizando descripción: {msg}")

    # Cambiar estado si se indicó
    if status:
        transitions = client.get_transitions(issue_key)
        transition = next(
            (t for t in transitions if t["name"].lower() == status.lower()),
            None
        )
        if transition:
            success, msg = client.transition_issue(issue_key, transition["id"])
            if success:
                print(f"  OK: Estado cambiado a '{status}'")
            else:
                print(f"  Error cambiando estado: {msg}")
        else:
            print(f"  Error: Transición '{status}' no disponible")

    return True


def batch_upload(client, mapping_path, golden_path, manifest, validation_user=None,
                 as_comment=False, dry_run=False, status=None):
    """
    Sube tests en batch usando un archivo de mapping.

    Formato del mapping (JSON):
    {
        "test-id": "JIRA-KEY",
        "home": "TGFDEV-100",
        "products": "TGFDEV-101"
    }
    """
    if not os.path.exists(mapping_path):
        print(f"Error: Archivo de mapping no encontrado: {mapping_path}")
        return

    with open(mapping_path, "r") as f:
        mapping = json.load(f)

    print(f"Procesando {len(mapping)} tests del mapping...")
    ok = 0
    errors = 0

    for test_id, issue_key in mapping.items():
        test = find_test(manifest, test_id)
        if not test:
            print(f"  Aviso: Test '{test_id}' no encontrado en manifest, ignorando")
            errors += 1
            continue

        try:
            upload_test(client, issue_key, test, golden_path, validation_user,
                        as_comment, dry_run, status)
            ok += 1
        except Exception as e:
            print(f"  Error procesando {test_id} → {issue_key}: {e}")
            errors += 1

    print(f"\nResumen: {ok} exitosos, {errors} errores")


def main():
    parser = argparse.ArgumentParser(
        description="Subir resultados de golden tests a Jira"
    )
    parser.add_argument("issue", nargs="?",
                        help="Clave de la issue (ej: TGFDEV-123)")
    parser.add_argument("--test", "-t",
                        help="ID del test (ej: home, products, career)")
    parser.add_argument("--images", nargs="+",
                        help="Imágenes custom a adjuntar (sin usar manifest)")
    parser.add_argument("--description", "-d",
                        help="Descripción custom (en vez de la generada)")
    parser.add_argument("--status", "-s",
                        help="Cambiar estado de la issue")
    parser.add_argument("--as-comment", action="store_true",
                        help="Subir como comentario en vez de actualizar descripción")
    parser.add_argument("--failed", action="store_true",
                        help="Subir todos los tests que fallaron")
    parser.add_argument("--validation", "-v",
                        help="Usar capturas de validación personal (ej: tincho)")
    parser.add_argument("--golden-path",
                        default=DEFAULT_GOLDEN_PATH,
                        help=f"Ruta al directorio de golden tests (default: {DEFAULT_GOLDEN_PATH})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostrar qué se haría sin ejecutar")
    parser.add_argument("--list", action="store_true",
                        help="Listar tests disponibles")
    parser.add_argument("--batch", action="store_true",
                        help="Modo batch usando archivo de mapping")
    parser.add_argument("--mapping", "-m",
                        help="Archivo JSON con mapping test-id → jira-key")

    args = parser.parse_args()

    # Cargar manifest
    manifest = load_manifest(args.golden_path)

    # Listar tests
    if args.list:
        list_tests(manifest)
        return

    # Validar que hay issue key (excepto para --list)
    if not args.issue and not args.batch:
        parser.error("Se requiere la clave de la issue o --batch con --mapping")

    client = JiraClient()

    # Modo batch
    if args.batch:
        if not args.mapping:
            parser.error("--batch requiere --mapping con la ruta al archivo JSON")
        batch_upload(client, args.mapping, args.golden_path, manifest,
                     args.validation, args.as_comment, args.dry_run, args.status)
        return

    issue_key = args.issue

    # Subir imágenes custom (sin manifest)
    if args.images:
        print(f"Subiendo {len(args.images)} imágenes a {issue_key}...")
        for img_path in args.images:
            if args.dry_run:
                exists = "OK" if os.path.exists(img_path) else "NO ENCONTRADO"
                print(f"  [DRY RUN] {img_path} [{exists}]")
                continue

            success, result = client.add_attachment(issue_key, img_path)
            if success:
                filenames = [a.get("filename", "?") for a in result]
                print(f"  OK: {', '.join(filenames)}")
            else:
                print(f"  Error: {result}")

        # Descripción custom
        if args.description and not args.dry_run:
            if args.as_comment:
                success, result = client.add_comment(issue_key, args.description)
            else:
                success, msg = client.update_description(issue_key, args.description)
            print(f"  {'OK' if success else 'Error'}: {'Comentario' if args.as_comment else 'Descripción'}")

        # Status
        if args.status and not args.dry_run:
            transitions = client.get_transitions(issue_key)
            transition = next(
                (t for t in transitions if t["name"].lower() == args.status.lower()),
                None
            )
            if transition:
                success, msg = client.transition_issue(issue_key, transition["id"])
                if success:
                    print(f"  OK: Estado → {args.status}")
            else:
                print(f"  Error: Transición '{args.status}' no disponible")
        return

    # Subir todos los tests fallidos
    if args.failed:
        failed_tests = [t for t in manifest.get("tests", [])
                        if t.get("lastResult") == "FAIL"]
        if not failed_tests:
            print("No hay tests fallidos")
            return

        print(f"Tests fallidos: {len(failed_tests)}")
        for test in failed_tests:
            upload_test(client, issue_key, test, args.golden_path,
                        args.validation, args.as_comment, args.dry_run, args.status)
        return

    # Subir un test específico
    if args.test:
        test = find_test(manifest, args.test)
        if not test:
            print(f"Error: Test '{args.test}' no encontrado en manifest")
            print("Tests disponibles:")
            for t in manifest.get("tests", []):
                print(f"  - {t['id']}")
            sys.exit(1)

        upload_test(client, issue_key, test, args.golden_path,
                    args.validation, args.as_comment, args.dry_run, args.status)
        return

    # Si no se especificó test ni imágenes, mostrar info
    print("Error: Especificá --test, --images o --failed")
    parser.print_help()


if __name__ == "__main__":
    main()
