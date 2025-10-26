This is the 4th rebuild of the Chimera Multi Agent System.

USE VENV: always use source venv/bin/activate before you pip install ANYTHING, or run ANYTHING in python. 

v3 is in /Users/ericksonc/appdev/prometheus - a great deal of that is still quite good, and we'll be lifting significant portions of it wholesale- but only bit by bit, carefully considered, with the human in the loop. 

---

# Early Development Best Practices - Follow these until they're in place!

# Early-Stage App Patterns - Quick Reference

## 1. User IDs Everywhere
Add `user_id` column to every user-data table now:
```python
user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")  # Hardcoded for now
```

## 2. Timestamps on Everything
```sql
created_at TIMESTAMP DEFAULT NOW(),
updated_at TIMESTAMP DEFAULT NOW()
```
Update `updated_at` via trigger or application logic.

## 3. Use UUIDs
```python
from uuid import UUID, uuid4
id: UUID = uuid4()
```
Decide now and stick with it.

## 4. UTC Always
```python
from datetime import datetime, timezone
created_at = datetime.now(timezone.utc)  # Never naive datetime.now()
```
Convert to user timezone only for display.

## 5. Idempotency Keys
For messages, LLM calls, and any state-changing operations:
```python
class Message:
    idempotency_key: str  # Unique from client
    # Check if Pydantic AI provides this before rolling your own
```
Add unique constraint in database.

## 6. Structured Logging
```python
import logging
logger = logging.getLogger(__name__)

# Not: print(f"Something happened")
# But: logger.info("event_name", user_id=user_id, tokens=150)
```

## 7. API Versioning
```python
@app.route('/api/v1/documents')  # Include v1 from day one
```

## 8. Repository Pattern with User Scoping
```python
class DocumentRepository(ABC):
    @abstractmethod
    def get_document(self, user_id: UUID, doc_id: UUID) -> Document:
        pass

# Every query includes user_id
"SELECT * FROM documents WHERE user_id = ? AND id = ?"
```

## Database Naming Convention Rule

When creating table schemas, if a column name provided isn't the most common convention:
- **STOP and SUGGEST** the standard name before creating schema
- Example: "You've named this `creation_date`, but the most common convention is `created_at`. Would you like to use `created_at` instead?"
- Never silently accept non-standard names
- Never change names without explicit approval

Standard names to prefer:
- Timestamps: `created_at`, `updated_at`
- Soft deletes: `deleted_at`
- Foreign keys: `[table]_id` (e.g., `user_id`)
- Booleans: `is_[state]` (e.g., `is_active`)
- Tables: plural (e.g., `users`, `documents`)

## Golden Rules
- If changing it later means migrating every row → add it now
- If it prevents data loss or money loss → add it now  
- If it's just a feature → build it later.