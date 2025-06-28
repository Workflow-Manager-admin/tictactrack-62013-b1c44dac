import os
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Enum
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import enum


# ----- Settings & Environment ------
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "super-secret-jwt-key")
ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

DB_URI = os.environ.get("DB_URI") or os.environ.get("MYSQL_URL")
if not DB_URI:
    raise RuntimeError(
        "Missing DB connection string. Set DB_URI or MYSQL_URL in environment."
    )


# ---- SQLAlchemy setup (simulate importing models from the tic_tac_toe_database) ----
Base = declarative_base()


class GameStatus(enum.Enum):
    waiting = "waiting"
    active = "active"
    finished = "finished"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True, nullable=False)
    email = Column(String(128), unique=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)


class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True)
    player_x_id = Column(Integer, ForeignKey("users.id"))
    player_o_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(Enum(GameStatus), default=GameStatus.waiting)
    created_at = Column(DateTime, default=datetime.utcnow)
    board = Column(String(9), default=" " * 9)  # 9 chars for tic tac toe board
    current_turn = Column(String(1), default="X")
    winner = Column(String(1), nullable=True)  # "X", "O", or "D" for draw


class Move(Base):
    __tablename__ = "moves"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    position = Column(Integer, nullable=False)
    marker = Column(String(1), nullable=False)  # X or O
    played_at = Column(DateTime, default=datetime.utcnow)


# ---- Database Session ----
engine = create_engine(DB_URI, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ---- Password hashing and Auth helpers ----
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


# ---- Pydantic Schemas ----
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(..., min_length=5)


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr

    class Config:
        orm_mode = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GameCreate(BaseModel):
    pass


class GameJoinRequest(BaseModel):
    game_id: int


class GameMove(BaseModel):
    position: int = Field(..., ge=0, le=8)


class MoveRead(BaseModel):
    position: int
    marker: str
    played_at: datetime

    class Config:
        orm_mode = True


class GameRead(BaseModel):
    id: int
    player_x: Optional[int]
    player_o: Optional[int]
    status: GameStatus
    board: str
    current_turn: str
    winner: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True


class GameListRead(BaseModel):
    id: int
    status: GameStatus
    current_turn: str
    winner: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True


class GameHistory(BaseModel):
    game: GameRead
    moves: List[MoveRead]


# ---- Utility functions ----
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain: str, hashed: str):
    return pwd_context.verify(plain, hashed)


def hash_password(password: str):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_from_token(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


# ---- FastAPI App setup ----
app = FastAPI(
    title="Tic Tac Toe API",
    description="Backend API for playing Tic Tac Toe with authentication and history.",
    version="1.0.0",
    openapi_tags=[
        {"name": "auth", "description": "User signup/login and authentication"},
        {"name": "user", "description": "User-related operations"},
        {"name": "game", "description": "Game actions, status, move submission, history"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Auth endpoints ----
# PUBLIC_INTERFACE
@app.post(
    "/auth/signup",
    response_model=UserRead,
    tags=["auth"],
    summary="Create a new user account",
    description="Register new user with username, email, and password.",
)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    if db.query(User).filter(
        (User.username == user.username) | (User.email == user.email)
    ).first():
        raise HTTPException(
            status_code=400, detail="Username or email already in use"
        )
    hashed_pw = hash_password(user.password)
    db_user = User(username=user.username, email=user.email, hashed_password=hashed_pw)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# PUBLIC_INTERFACE
@app.post(
    "/auth/token", response_model=Token, tags=["auth"], summary="Login and get JWT token"
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """Authenticate and return JWT token."""
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401, detail="Incorrect username or password"
        )
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


# ---- User endpoints ----
# PUBLIC_INTERFACE
@app.get(
    "/user/me", response_model=UserRead, tags=["user"], summary="Return current user"
)
def read_users_me(current_user: User = Depends(get_user_from_token)):
    """Get information about the current authenticated user."""
    return current_user


# ---- Game endpoints ----
# PUBLIC_INTERFACE
@app.post(
    "/games/",
    response_model=GameRead,
    tags=["game"],
    summary="Create a new game",
    description="Create a new Tic Tac Toe game. Authenticated user will be assigned as player X.",
)
def create_game(
    current_user: User = Depends(get_user_from_token), db: Session = Depends(get_db)
):
    """Create a new game with the authenticated user as player X."""
    game = Game(
        player_x_id=current_user.id,
        board=" " * 9,
        current_turn="X",
        status=GameStatus.waiting,
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return _game_to_schema(game)


# PUBLIC_INTERFACE
@app.post(
    "/games/join",
    response_model=GameRead,
    tags=["game"],
    summary="Join an existing game",
    description="Join an open Tic Tac Toe game as player O.",
)
def join_game(
    req: GameJoinRequest,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_db),
):
    game = db.query(Game).filter(Game.id == req.game_id).first()
    if not game or game.status != GameStatus.waiting:
        raise HTTPException(status_code=400, detail="Game not available to join.")
    if game.player_x_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot join your own game.")
    game.player_o_id = current_user.id
    game.status = GameStatus.active
    db.commit()
    db.refresh(game)
    return _game_to_schema(game)


# PUBLIC_INTERFACE
@app.get(
    "/games/active",
    response_model=List[GameListRead],
    tags=["game"],
    summary="List active games for the user",
)
def list_active_games(
    current_user: User = Depends(get_user_from_token), db: Session = Depends(get_db)
):
    games = (
        db.query(Game)
        .filter(
            ((Game.player_x_id == current_user.id) | (Game.player_o_id == current_user.id))
            & (Game.status != GameStatus.finished)
        )
        .all()
    )
    return [_game_to_schema_brief(g) for g in games]


# PUBLIC_INTERFACE
@app.get(
    "/games/history",
    response_model=List[GameListRead],
    tags=["game"],
    summary="List finished (history) games for the user",
)
def list_finished_games(
    current_user: User = Depends(get_user_from_token), db: Session = Depends(get_db)
):
    games = (
        db.query(Game)
        .filter(
            ((Game.player_x_id == current_user.id) | (Game.player_o_id == current_user.id))
            & (Game.status == GameStatus.finished)
        )
        .order_by(Game.created_at.desc())
        .all()
    )
    return [_game_to_schema_brief(g) for g in games]


# PUBLIC_INTERFACE
@app.get(
    "/games/{game_id}", response_model=GameRead, tags=["game"], summary="Get game details"
)
def get_game(
    game_id: int,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_db),
):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game or _game_forbidden(game, current_user.id):
        raise HTTPException(status_code=404, detail="Game not found")
    return _game_to_schema(game)


# PUBLIC_INTERFACE
@app.post(
    "/games/{game_id}/move",
    response_model=GameRead,
    tags=["game"],
    summary="Submit move for a game",
)
def submit_move(
    game_id: int,
    move: GameMove,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_db),
):
    """Submit a move to the board; validates turn, checks win/draw, updates board/moves."""
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game or _game_forbidden(game, current_user.id):
        raise HTTPException(
            status_code=404,
            detail="Game not found or access denied."
        )
    if game.status != GameStatus.active:
        raise HTTPException(
            status_code=400,
            detail="Game is not active."
        )
    marker = _get_marker_for_player(game, current_user.id)
    if marker != game.current_turn:
        raise HTTPException(
            status_code=400,
            detail="Not your turn."
        )
    if move.position < 0 or move.position > 8 or game.board[move.position] != " ":
        raise HTTPException(
            status_code=400,
            detail="Invalid move position."
        )
    game.board = (
        game.board[:move.position]
        + marker
        + game.board[move.position + 1:]
    )
    new_move = Move(
        game_id=game.id, user_id=current_user.id,
        position=move.position, marker=marker
    )
    winner = _check_winner(game.board)
    if winner:
        game.status = GameStatus.finished
        game.winner = winner if winner in ["X", "O"] else "D"
    else:
        game.current_turn = "O" if game.current_turn == "X" else "X"
        if " " not in game.board:
            game.status = GameStatus.finished
            game.winner = "D"
    db.add(new_move)
    db.commit()
    db.refresh(game)
    return _game_to_schema(game)


# PUBLIC_INTERFACE
@app.get(
    "/games/{game_id}/moves",
    response_model=List[MoveRead],
    tags=["game"],
    summary="List all moves for a game",
)
def get_game_moves(
    game_id: int,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_db),
):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game or _game_forbidden(game, current_user.id):
        raise HTTPException(status_code=404, detail="Game not found")
    moves = db.query(Move).filter(Move.game_id == game.id).order_by(Move.played_at).all()
    return [
        MoveRead(position=m.position, marker=m.marker, played_at=m.played_at)
        for m in moves
    ]


# PUBLIC_INTERFACE
@app.get(
    "/games/{game_id}/history",
    response_model=GameHistory,
    tags=["game"],
    summary="Full history of a single game",
)
def get_full_game_history(
    game_id: int,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_db),
):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game or _game_forbidden(game, current_user.id):
        raise HTTPException(status_code=404, detail="Game not found")
    moves = db.query(Move).filter(Move.game_id == game.id).order_by(Move.played_at).all()
    return {
        "game": _game_to_schema(game),
        "moves": [
            MoveRead(position=m.position, marker=m.marker, played_at=m.played_at)
            for m in moves
        ],
    }


# ---- Utility functions for game logic and conversion ----
def _game_to_schema(game: Game):
    """Convert a Game model to GameRead schema."""
    return GameRead(
        id=game.id,
        player_x=game.player_x_id,
        player_o=game.player_o_id,
        status=game.status,
        board=game.board,
        current_turn=game.current_turn,
        winner=game.winner,
        created_at=game.created_at,
    )


def _game_to_schema_brief(game: Game):
    """Convert to a minimal game list schema."""
    return GameListRead(
        id=game.id,
        status=game.status,
        current_turn=game.current_turn,
        winner=game.winner,
        created_at=game.created_at
    )


def _game_forbidden(game: Game, user_id: int):
    return user_id not in [game.player_x_id, game.player_o_id]


def _get_marker_for_player(game: Game, user_id: int):
    if game.player_x_id == user_id:
        return "X"
    elif game.player_o_id == user_id:
        return "O"
    else:
        raise HTTPException(status_code=403, detail="Not a player in this game.")


def _check_winner(board: str) -> Optional[str]:
    """Return 'X', 'O', or 'D' for draw, or None for no winner."""
    wins = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6)
    ]
    for i, j, k in wins:
        if board[i] != " " and board[i] == board[j] == board[k]:
            return board[i]
    if " " not in board:
        return "D"
    return None


# ---- App metadata / root endpoint ----
@app.get("/", tags=["root"], summary="API Health/Index")
def health_check():
    """Health check endpoint for Tic Tac Toe backend API."""
    return {"message": "Healthy"}


# ---- Custom OpenAPI (optional: to show proper JWT usage in docs) ----
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
