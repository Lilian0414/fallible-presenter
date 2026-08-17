from ..models import PresentationSession


class MemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[str, PresentationSession] = {}

    def add(self, session: PresentationSession) -> None:
        self.sessions[session.id] = session

    def get(self, session_id: str) -> PresentationSession | None:
        return self.sessions.get(session_id)

    def clear(self) -> None:
        self.sessions.clear()


store = MemoryStore()
