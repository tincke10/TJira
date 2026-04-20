# Estructura CSV para Importacion de Worklogs

## Columnas

| Columna | Requerida | Formato | Descripcion |
|---------|-----------|---------|-------------|
| `Jira Key` | Si | `PROJ-123` | Clave de la issue en Jira |
| `Task ID` | No | Texto libre | ID interno de referencia |
| `Summary` | No | Texto libre | Descripcion corta de la tarea |
| `Date` | No | Texto libre | Referencia visual del dia |
| `Started` | Si | ISO 8601 | Fecha y hora de inicio del worklog |
| `Time Spent` | Si | `Xh`, `Xm`, `Xh Xm` | Duracion del trabajo registrado |
| `Author` | No | Email | Email del autor del worklog |

## Formato del campo Started

```
YYYY-MM-DDTHH:MM:SS.000+0100
```

Ejemplo: `2026-02-18T09:00:00.000+0100`

## Formato del campo Time Spent

| Ejemplo | Significado |
|---------|-------------|
| `1h` | 1 hora |
| `30m` | 30 minutos |
| `2h 30m` | 2 horas y 30 minutos |
| `4h` | 4 horas |

## Ejemplo CSV

```csv
Jira Key,Task ID,Summary,Date,Started,Time Spent,Author
TGFDEV-101,T-001,Diseño de base de datos,Lunes 18/02,2026-02-18T09:00:00.000+0100,4h,juan@empresa.com
TGFDEV-101,T-001,Diseño de base de datos,Lunes 18/02,2026-02-18T14:00:00.000+0100,2h,juan@empresa.com
TGFDEV-102,T-002,Implementar API REST,Martes 19/02,2026-02-19T09:00:00.000+0100,3h,juan@empresa.com
TGFDEV-102,T-002,Implementar API REST,Martes 19/02,2026-02-19T13:00:00.000+0100,3h 30m,juan@empresa.com
TGFDEV-103,T-003,Code review PR #45,Miercoles 20/02,2026-02-20T10:00:00.000+0100,1h 30m,juan@empresa.com
TGFDEV-104,T-004,Fix bug login timeout,Miercoles 20/02,2026-02-20T14:00:00.000+0100,2h,juan@empresa.com
```

## Comandos

```bash
# Previsualizar sin ejecutar
python import_worklogs.py archivo.csv --dry-run

# Importar
python import_worklogs.py archivo.csv

# Eliminar worklogs importados
python delete_worklogs.py archivo.csv --dry-run
python delete_worklogs.py archivo.csv
```
