"""Cliente de Jira API - Clase reutilizable para todas las operaciones."""

import requests
from requests.auth import HTTPBasicAuth
from typing import Optional
from config import JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, validate_config


class JiraClient:
    """Cliente para interactuar con la API de Jira."""

    def __init__(self):
        validate_config()
        self.base_url = f"https://{JIRA_DOMAIN}/rest/api/3"
        self.auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _request(self, method: str, endpoint: str, data: dict = None) -> requests.Response:
        """Realiza una petición a la API de Jira."""
        url = f"{self.base_url}/{endpoint}"
        return requests.request(
            method=method,
            url=url,
            headers=self.headers,
            auth=self.auth,
            json=data
        )

    # ==================== ISSUES ====================

    def get_issue(self, issue_key: str) -> Optional[dict]:
        """Obtiene información de una issue."""
        response = self._request("GET", f"issue/{issue_key}")
        if response.status_code == 200:
            return response.json()
        return None

    def create_issue(self, project_key: str, summary: str, issue_type: str = "Task",
                     description: str = None, assignee_id: str = None) -> tuple[bool, dict]:
        """
        Crea una nueva issue.

        Args:
            project_key: Clave del proyecto (ej: "TGFDEV")
            summary: Título de la tarea
            issue_type: Tipo de issue (Task, Bug, Story, etc.)
            description: Descripción opcional
            assignee_id: ID del usuario asignado (opcional)

        Returns:
            Tupla (éxito, respuesta/error)
        """
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type}
            }
        }

        if description:
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}]
                }]
            }

        if assignee_id:
            payload["fields"]["assignee"] = {"id": assignee_id}

        response = self._request("POST", "issue", payload)

        if response.status_code == 201:
            return True, response.json()
        return False, {"error": response.text, "status": response.status_code}

    def update_issue(self, issue_key: str, fields: dict) -> tuple[bool, str]:
        """
        Actualiza una issue.

        Args:
            issue_key: Clave de la issue (ej: "TGFDEV-123")
            fields: Diccionario con los campos a actualizar

        Returns:
            Tupla (éxito, mensaje)
        """
        payload = {"fields": fields}
        response = self._request("PUT", f"issue/{issue_key}", payload)

        if response.status_code == 204:
            return True, "Issue actualizada correctamente"
        return False, response.text

    def transition_issue(self, issue_key: str, transition_id: str) -> tuple[bool, str]:
        """
        Cambia el estado de una issue.

        Args:
            issue_key: Clave de la issue
            transition_id: ID de la transición

        Returns:
            Tupla (éxito, mensaje)
        """
        payload = {"transition": {"id": transition_id}}
        response = self._request("POST", f"issue/{issue_key}/transitions", payload)

        if response.status_code == 204:
            return True, "Transición realizada"
        return False, response.text

    def get_transitions(self, issue_key: str) -> list:
        """Obtiene las transiciones disponibles para una issue."""
        response = self._request("GET", f"issue/{issue_key}/transitions")
        if response.status_code == 200:
            return response.json().get("transitions", [])
        return []

    def assign_issue(self, issue_key: str, assignee_id: str) -> tuple[bool, str]:
        """Asigna una issue a un usuario."""
        payload = {"accountId": assignee_id}
        response = self._request("PUT", f"issue/{issue_key}/assignee", payload)

        if response.status_code == 204:
            return True, "Issue asignada correctamente"
        return False, response.text

    # ==================== WORKLOGS ====================

    def get_worklogs(self, issue_key: str) -> list:
        """Obtiene los worklogs de una issue."""
        response = self._request("GET", f"issue/{issue_key}/worklog")
        if response.status_code == 200:
            return response.json().get("worklogs", [])
        return []

    def add_worklog(self, issue_key: str, time_spent: str,
                    started: str = None, comment: str = None) -> tuple[bool, dict]:
        """
        Añade un worklog a una issue.

        Args:
            issue_key: Clave de la issue
            time_spent: Tiempo gastado (ej: "2h", "30m", "1h 30m")
            started: Fecha/hora de inicio ISO 8601 (opcional)
            comment: Comentario opcional

        Returns:
            Tupla (éxito, respuesta/error)
        """
        payload = {"timeSpent": time_spent}

        if started:
            payload["started"] = started

        if comment:
            payload["comment"] = {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment}]
                }]
            }

        response = self._request("POST", f"issue/{issue_key}/worklog", payload)

        if response.status_code == 201:
            return True, response.json()
        return False, {"error": response.text, "status": response.status_code}

    def delete_worklog(self, issue_key: str, worklog_id: str) -> bool:
        """Elimina un worklog."""
        response = self._request("DELETE", f"issue/{issue_key}/worklog/{worklog_id}")
        return response.status_code == 204

    # ==================== BÚSQUEDA ====================

    def search_issues(self, jql: str, max_results: int = 50) -> list:
        """
        Busca issues usando JQL.

        Args:
            jql: Query JQL (ej: "project = TGFDEV AND status = 'In Progress'")
            max_results: Máximo de resultados

        Returns:
            Lista de issues
        """
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "issuetype", "priority"]
        }
        response = self._request("POST", "search", payload)

        if response.status_code == 200:
            return response.json().get("issues", [])
        return []

    # ==================== USUARIOS ====================

    def get_myself(self) -> Optional[dict]:
        """Obtiene información del usuario autenticado."""
        response = self._request("GET", "myself")
        if response.status_code == 200:
            return response.json()
        return None

    def search_users(self, query: str) -> list:
        """Busca usuarios por nombre o email."""
        response = self._request("GET", f"user/search?query={query}")
        if response.status_code == 200:
            return response.json()
        return []

    # ==================== PROYECTOS ====================

    def get_projects(self) -> list:
        """Obtiene la lista de proyectos accesibles."""
        response = self._request("GET", "project")
        if response.status_code == 200:
            return response.json()
        return []

    def get_project(self, project_key: str) -> Optional[dict]:
        """Obtiene información de un proyecto."""
        response = self._request("GET", f"project/{project_key}")
        if response.status_code == 200:
            return response.json()
        return None
