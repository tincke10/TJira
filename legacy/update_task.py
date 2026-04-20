#!/usr/bin/env python3
"""
Script para actualizar tareas en Jira.

Uso:
    python update_task.py TGFDEV-123                              # Ver info de la tarea
    python update_task.py TGFDEV-123 --summary "Nuevo título"
    python update_task.py TGFDEV-123 --status "In Progress"
    python update_task.py TGFDEV-123 --assign me
    python update_task.py TGFDEV-123 --transitions                # Ver transiciones
    python update_task.py TGFDEV-123 --description "Texto de la descripción"
    python update_task.py TGFDEV-123 --desc-file descripcion.txt  # Descripción desde archivo
    python update_task.py TGFDEV-123 --attach imagen.png          # Adjuntar archivo
    python update_task.py TGFDEV-123 --comment "Un comentario"
    python update_task.py TGFDEV-123 --golden-test "Resultado del golden test" --attach captura.png
"""

import sys
import argparse
from jira_client import JiraClient


def main():
    parser = argparse.ArgumentParser(description="Actualizar una tarea en Jira")
    parser.add_argument("issue", help="Clave de la issue (ej: TGFDEV-123)")
    parser.add_argument("--summary", "-s", help="Nuevo título")
    parser.add_argument("--status", help="Cambiar estado (ver transiciones disponibles)")
    parser.add_argument("--assign", "-a", help="Asignar a usuario (ID o 'me')")
    parser.add_argument("--transitions", action="store_true",
                        help="Mostrar transiciones disponibles")

    # Descripción
    parser.add_argument("--description", "-d",
                        help="Actualizar descripción (texto)")
    parser.add_argument("--desc-file",
                        help="Actualizar descripción desde un archivo de texto")

    # Adjuntos
    parser.add_argument("--attach", nargs="+",
                        help="Adjuntar uno o más archivos (ej: --attach img.png doc.pdf)")

    # Comentarios
    parser.add_argument("--comment", "-c",
                        help="Añadir un comentario a la issue")

    # Golden Test (atajo: descripción + imagen)
    parser.add_argument("--golden-test",
                        help="Descripción del golden test (usar con --attach para la imagen)")

    args = parser.parse_args()

    client = JiraClient()
    issue_key = args.issue
    action_taken = False

    # Mostrar transiciones disponibles
    if args.transitions:
        print(f"Transiciones disponibles para {issue_key}:")
        transitions = client.get_transitions(issue_key)
        for t in transitions:
            print(f"  [{t['id']}] {t['name']}")
        return

    # Actualizar título
    if args.summary:
        success, msg = client.update_issue(issue_key, {"summary": args.summary})
        if success:
            print(f"OK: Título actualizado")
        else:
            print(f"Error actualizando título: {msg}")
        action_taken = True

    # Cambiar estado
    if args.status:
        transitions = client.get_transitions(issue_key)
        transition = next(
            (t for t in transitions if t["name"].lower() == args.status.lower()),
            None
        )

        if transition:
            success, msg = client.transition_issue(issue_key, transition["id"])
            if success:
                print(f"OK: Estado cambiado a '{args.status}'")
            else:
                print(f"Error cambiando estado: {msg}")
        else:
            print(f"Error: Transición '{args.status}' no disponible")
            print("Transiciones disponibles:")
            for t in transitions:
                print(f"  - {t['name']}")
        action_taken = True

    # Asignar usuario
    if args.assign:
        assignee_id = args.assign
        if args.assign.lower() == "me":
            me = client.get_myself()
            if me:
                assignee_id = me.get("accountId")
            else:
                print("Error: No se pudo obtener tu ID de usuario")
                sys.exit(1)

        success, msg = client.assign_issue(issue_key, assignee_id)
        if success:
            print(f"OK: Issue asignada")
        else:
            print(f"Error asignando: {msg}")
        action_taken = True

    # Actualizar descripción (texto directo)
    if args.description:
        success, msg = client.update_description(issue_key, args.description)
        if success:
            print(f"OK: Descripción actualizada")
        else:
            print(f"Error actualizando descripción: {msg}")
        action_taken = True

    # Actualizar descripción desde archivo
    if args.desc_file:
        try:
            with open(args.desc_file, "r", encoding="utf-8") as f:
                desc_text = f.read()
            success, msg = client.update_description(issue_key, desc_text)
            if success:
                print(f"OK: Descripción actualizada desde '{args.desc_file}'")
            else:
                print(f"Error actualizando descripción: {msg}")
        except FileNotFoundError:
            print(f"Error: Archivo no encontrado: {args.desc_file}")
        action_taken = True

    # Golden test (descripción + imagen)
    if args.golden_test:
        success, msg = client.update_description(issue_key, args.golden_test)
        if success:
            print(f"OK: Descripción del golden test actualizada")
        else:
            print(f"Error actualizando descripción del golden test: {msg}")
        action_taken = True

    # Adjuntar archivos
    if args.attach:
        for file_path in args.attach:
            success, result = client.add_attachment(issue_key, file_path)
            if success:
                filenames = [a.get("filename", "?") for a in result]
                print(f"OK: Archivo adjuntado: {', '.join(filenames)}")
            else:
                print(f"Error adjuntando '{file_path}': {result}")
        action_taken = True

    # Añadir comentario
    if args.comment:
        success, result = client.add_comment(issue_key, args.comment)
        if success:
            print(f"OK: Comentario añadido (ID: {result.get('id', '?')})")
        else:
            print(f"Error añadiendo comentario: {result}")
        action_taken = True

    # Si no se proporcionó ninguna acción, mostrar info de la issue
    if not action_taken:
        issue = client.get_issue(issue_key)
        if issue:
            fields = issue["fields"]
            print(f"Issue: {issue_key}")
            print(f"  Título: {fields.get('summary')}")
            print(f"  Tipo: {fields.get('issuetype', {}).get('name')}")
            print(f"  Estado: {fields.get('status', {}).get('name')}")
            assignee = fields.get('assignee')
            print(f"  Asignado: {assignee.get('displayName') if assignee else 'Sin asignar'}")

            # Mostrar descripción si existe
            desc = fields.get("description")
            if desc and desc.get("content"):
                print(f"  Descripción:")
                for block in desc["content"]:
                    if block.get("type") == "paragraph":
                        for item in block.get("content", []):
                            if item.get("type") == "text":
                                print(f"    {item['text']}")

            # Mostrar adjuntos si existen
            attachments = fields.get("attachment", [])
            if attachments:
                print(f"  Adjuntos ({len(attachments)}):")
                for att in attachments:
                    print(f"    - {att.get('filename')} ({att.get('size', 0) // 1024}KB)")
        else:
            print(f"Error: No se encontró la issue {issue_key}")


if __name__ == "__main__":
    main()
