"""Cliente de Jira API - Clase reutilizable para todas las operaciones."""

import os
import requests
from requests.auth import HTTPBasicAuth
from typing import Optional
from config import JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, validate_config


class JiraClient:
    """Cliente para interactuar con la API de Jira."""

    def __init__(self):
        validate_config()
        self.base_url = f"https://{JIRA_DOMAIN}/rest/api/3"
        self.agile_url = f"https://{JIRA_DOMAIN}/rest/agile/1.0"
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

    def _request_agile(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> requests.Response:
        """Realiza una petición a la API Agile de Jira."""
        url = f"{self.agile_url}/{endpoint}"
        return requests.request(
            method=method,
            url=url,
            headers=self.headers,
            auth=self.auth,
            json=data,
            params=params
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

    # ==================== BOARDS (AGILE) ====================

    def get_boards(self, project_key: str = None, board_type: str = None) -> list:
        """
        Lista los boards de Jira (Scrum/Kanban).

        Args:
            project_key: Filtrar por proyecto (opcional)
            board_type: Filtrar por tipo: 'scrum', 'kanban' (opcional)

        Returns:
            Lista de boards
        """
        params = {}
        if project_key:
            params["projectKeyOrId"] = project_key
        if board_type:
            params["type"] = board_type

        response = self._request_agile("GET", "board", params=params)
        if response.status_code == 200:
            return response.json().get("values", [])
        return []

    def get_board_issues(self, board_id: int, max_results: int = 50, jql: str = None) -> list:
        """
        Obtiene las issues de un board.

        Args:
            board_id: ID del board
            max_results: Máximo de resultados
            jql: Filtro JQL adicional (opcional)

        Returns:
            Lista de issues
        """
        params = {"maxResults": max_results}
        if jql:
            params["jql"] = jql

        response = self._request_agile("GET", f"board/{board_id}/issue", params=params)
        if response.status_code == 200:
            return response.json().get("issues", [])
        return []

    def get_board_sprints(self, board_id: int, state: str = "active") -> list:
        """
        Obtiene los sprints de un board.

        Args:
            board_id: ID del board
            state: Estado del sprint: 'active', 'closed', 'future'

        Returns:
            Lista de sprints
        """
        params = {"state": state}
        response = self._request_agile("GET", f"board/{board_id}/sprint", params=params)
        if response.status_code == 200:
            return response.json().get("values", [])
        return []

    def get_sprint_issues(self, sprint_id: int, max_results: int = 50) -> list:
        """Obtiene las issues de un sprint."""
        params = {"maxResults": max_results}
        response = self._request_agile("GET", f"sprint/{sprint_id}/issue", params=params)
        if response.status_code == 200:
            return response.json().get("issues", [])
        return []

    # ==================== FILTROS ====================

    def get_filters(self, filter_name: str = None) -> list:
        """
        Busca filtros guardados.

        Args:
            filter_name: Nombre del filtro a buscar (opcional)

        Returns:
            Lista de filtros
        """
        params = {"expand": "jql"}
        if filter_name:
            params["filterName"] = filter_name

        response = self._request("GET", f"filter/search?{'&'.join(f'{k}={v}' for k, v in params.items())}")
        if response.status_code == 200:
            return response.json().get("values", [])
        return []

    def get_filter(self, filter_id: int) -> Optional[dict]:
        """Obtiene un filtro por ID (incluye el JQL)."""
        response = self._request("GET", f"filter/{filter_id}")
        if response.status_code == 200:
            return response.json()
        return None

    def get_filter_issues(self, filter_id: int, max_results: int = 50) -> list:
        """Obtiene las issues de un filtro ejecutando su JQL."""
        filter_data = self.get_filter(filter_id)
        if filter_data and "jql" in filter_data:
            return self.search_issues(filter_data["jql"], max_results)
        return []

    # ==================== DASHBOARDS ====================

    def get_dashboards(self, filter_name: str = None) -> list:
        """
        Lista los dashboards disponibles.

        Args:
            filter_name: Filtrar por nombre (opcional)

        Returns:
            Lista de dashboards
        """
        params = ""
        if filter_name:
            params = f"?filter={filter_name}"

        response = self._request("GET", f"dashboard{params}")
        if response.status_code == 200:
            return response.json().get("dashboards", [])
        return []

    # ==================== ATTACHMENTS ====================

    def add_attachment(self, issue_key: str, file_path: str) -> tuple[bool, dict]:
        """
        Adjunta un archivo a una issue.

        Args:
            issue_key: Clave de la issue (ej: "TGFDEV-123")
            file_path: Ruta al archivo a adjuntar

        Returns:
            Tupla (éxito, respuesta/error)
        """
        if not os.path.exists(file_path):
            return False, {"error": f"Archivo no encontrado: {file_path}"}

        url = f"{self.base_url}/issue/{issue_key}/attachments"
        headers = {
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check"
        }

        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f)}
            response = requests.post(
                url,
                headers=headers,
                auth=self.auth,
                files=files
            )

        if response.status_code == 200:
            return True, response.json()
        return False, {"error": response.text, "status": response.status_code}

    # ==================== DESCRIPCIÓN ====================

    def update_description(self, issue_key: str, description: str) -> tuple[bool, str]:
        """
        Actualiza la descripción de una issue con texto plano.

        Args:
            issue_key: Clave de la issue
            description: Texto de la descripción

        Returns:
            Tupla (éxito, mensaje)
        """
        fields = {
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}]
                }]
            }
        }
        return self.update_issue(issue_key, fields)

    def update_description_adf(self, issue_key: str, adf_content: dict) -> tuple[bool, str]:
        """
        Actualiza la descripción con contenido ADF (Atlassian Document Format).

        Args:
            issue_key: Clave de la issue
            adf_content: Contenido en formato ADF

        Returns:
            Tupla (éxito, mensaje)
        """
        fields = {"description": adf_content}
        return self.update_issue(issue_key, fields)

    # ==================== COMENTARIOS ====================

    def add_comment(self, issue_key: str, body: str) -> tuple[bool, dict]:
        """
        Añade un comentario a una issue.

        Args:
            issue_key: Clave de la issue
            body: Texto del comentario

        Returns:
            Tupla (éxito, respuesta/error)
        """
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": body}]
                }]
            }
        }
        response = self._request("POST", f"issue/{issue_key}/comment", payload)

        if response.status_code == 201:
            return True, response.json()
        return False, {"error": response.text, "status": response.status_code}
