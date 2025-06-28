# Tic Tac Toe Backend

This backend provides RESTful APIs for Tic Tac Toe gameplay, user authentication, game state management, and history persistence.

## Features

- **User Signup/Login** (JWT, `/auth/signup`, `/auth/token`, `/user/me`)
- **Game Creation & Join** (`/games/`, `/games/join`)
- **Move Submission & Validation** (`/games/{game_id}/move`)
- **Game State Management** (tracks current turn, board, win/draw)
- **Active & Past Games Listing** (`/games/active`, `/games/history`)
- **Game History Tracking** (`/games/{game_id}/history`)
- **OpenAPI docs**: `/docs`

## Setup

- Requires Python 3.10+ (FastAPI, SQLAlchemy, passlib, python-jose)
- Configure DB via `MYSQL_URL` or `DB_URI` env variable (integrated with tic_tac_toe_database)
- JWT secret/config via `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`
- Install dependencies:

    ```
    pip install -r requirements.txt
    ```

- Start server:

    ```
    uvicorn src.api.main:app --reload
    ```

- Visit `/docs` for API usage.

## Endpoints

Major endpoints:
- `POST /auth/signup` - User registration
- `POST /auth/token` - Login, get JWT
- `GET /user/me` - Current user
- `POST /games/` - Create game
- `POST /games/join` - Join game as second player
- `POST /games/{game_id}/move` - Submit move
- `GET /games/active` - List in-progress games for user
- `GET /games/history` - List finished games for user
- `GET /games/{game_id}` - Get game details
- `GET /games/{game_id}/history` - Game history

## Database Integration

- Uses SQLAlchemy models matching tic_tac_toe_database schema.
- All state and moves persisted in tic_tac_toe_database.

## Testing

- See docs and try endpoints using `/docs` (Swagger UI).

