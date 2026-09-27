import socket
import json
import threading
import time

from game.game import Game


HOST = "0.0.0.0"
PORT = 5000

game = Game()

game_state = "WAITING"

serving_player = None

clients = {}

player_inputs = {
    1: "none",
    2: "none"
}

lock = threading.Lock()


# --------------------------------------------------
# SEND MESSAGE
# --------------------------------------------------

def send_message(client, message):
    """Send a JSON message with newline framing."""

    data = json.dumps(message) + "\n"

    client.sendall(
        data.encode()
    )


# --------------------------------------------------
# SEND TO ALL CLIENTS
# --------------------------------------------------

def broadcast(message):
    """Send a message to all connected clients."""

    data = json.dumps(message) + "\n"
    encoded_message = data.encode()

    with lock:
        current_clients = list(
            clients.items()
        )

    for player_number, client in current_clients:

        try:

            client.sendall(
                encoded_message
            )

        except ConnectionError:

            print(
                f"Player {player_number} disconnected"
            )

            with lock:

                if player_number in clients:
                    del clients[player_number]

                player_inputs[
                    player_number
                ] = "none"


# --------------------------------------------------
# SEND GAME STATE
# --------------------------------------------------

def send_state():
    """Send the current game state to all clients."""

    with lock:

        state = {
            "type": "state",

            "game_state":
                game_state,

            "player1_y":
                game.player1.paddle.y,

            "player2_y":
                game.player2.paddle.y,

            "ball_x":
                game.ball.x,

            "ball_y":
                game.ball.y,

            "score1":
                game.player1.score,

            "score2":
                game.player2.score,

            "last_point":
                game.last_point,

            "serving_player":
                serving_player
        }

        current_clients = list(
            clients.items()
        )

    message = json.dumps(state) + "\n"
    encoded_message = message.encode()

    for player_number, client in current_clients:

        try:

            client.sendall(
                encoded_message
            )

        except ConnectionError:

            print(
                f"Player {player_number} disconnected"
            )

            with lock:

                if player_number in clients:
                    del clients[player_number]

                player_inputs[
                    player_number
                ] = "none"


# --------------------------------------------------
# CLIENT HANDLER
# --------------------------------------------------

def handle_client(client, player_number):

    global game_state
    global serving_player

    print(
        f"Player {player_number} connected"
    )

    # Tell client which player they are

    try:

        send_message(
            client,
            {
                "type": "welcome",
                "player": player_number
            }
        )

    except ConnectionError:

        client.close()
        return

    buffer = ""

    try:

        while True:

            data = client.recv(1024)

            if not data:
                break

            buffer += data.decode(
                errors="replace"
            )

            while "\n" in buffer:

                line, buffer = buffer.split(
                    "\n",
                    1
                )

                if not line:
                    continue

                # Message size limit

                if len(line) > 4096:

                    print(
                        f"Player {player_number}: "
                        "message too large"
                    )

                    continue

                # Parse JSON

                try:

                    message = json.loads(line)

                except json.JSONDecodeError:

                    print(
                        f"Player {player_number}: "
                        "invalid JSON"
                    )

                    continue

                # --------------------------------------------------
                # INPUT
                # --------------------------------------------------

                if message.get("type") != "input":
                    continue

                direction = message.get(
                    "direction"
                )

                # Normal movement

                if direction in (
                    "up",
                    "down",
                    "none"
                ):

                    with lock:

                        player_inputs[
                            player_number
                        ] = direction

                # Start game

                elif direction == "start":

                    with lock:

                        if (
                            game_state == "READY"
                            and
                            serving_player
                            == player_number
                        ):

                            game.ball.launch()

                            game_state = "PLAYING"

                            print(
                                f"Player {player_number} "
                                "started the game"
                            )


    except ConnectionError:

        pass


    finally:

        with lock:

            if player_number in clients:

                del clients[
                    player_number
                ]

            player_inputs[
                player_number
            ] = "none"

            game_state = "WAITING"

            serving_player = None

        client.close()

        print(
            f"Player {player_number} disconnected"
        )


# --------------------------------------------------
# SERVER SOCKET
# --------------------------------------------------

server = socket.socket(
    socket.AF_INET,
    socket.SOCK_STREAM
)

server.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR,
    1
)

server.bind(
    (HOST, PORT)
)

server.listen(2)

print(
    f"Server listening on 0.0.0.0:{PORT}"
)


last_time = time.perf_counter()


# --------------------------------------------------
# MAIN GAME LOOP
# --------------------------------------------------

while True:

    server.settimeout(
        0.001
    )

    try:

        client, address = server.accept()

    except socket.timeout:

        client = None


    # --------------------------------------------------
    # NEW CLIENT
    # --------------------------------------------------

    if client is not None:

        with lock:

            if 1 not in clients:

                player_number = 1

            elif 2 not in clients:

                player_number = 2

            else:

                player_number = None


            if player_number is not None:

                clients[
                    player_number
                ] = client


        # Game is full

        if player_number is None:

            try:

                send_message(
                    client,
                    {
                        "type": "error",
                        "message": "Game is full"
                    }
                )

            except ConnectionError:

                pass

            client.close()


        else:

            print(
                f"Player {player_number} "
                f"connected from {address}"
            )

            thread = threading.Thread(
                target=handle_client,
                args=(
                    client,
                    player_number
                ),
                daemon=True
            )

            thread.start()


    # --------------------------------------------------
    # CHECK PLAYER COUNT
    # --------------------------------------------------

    with lock:

        player_count = len(
            clients
        )


    # --------------------------------------------------
    # TWO PLAYERS CONNECTED
    # --------------------------------------------------

    if (
        player_count == 2
        and game_state == "WAITING"
    ):

        game = Game()

        with lock:

            player_inputs[1] = "none"
            player_inputs[2] = "none"

            # Player 1 starts

            serving_player = 1

            # Ball is attached to Player 1

            game.ball.attach_to_paddle(
                game.player1.paddle
            )

            game_state = "READY"

        print(
            "Both players connected!"
        )

        print(
            "Player 1 starts."
        )

        broadcast(
            {
                "type": "game_event",
                "event": "ready",
                "serving_player": 1
            }
        )


    # --------------------------------------------------
    # DELTA TIME
    # --------------------------------------------------

    current_time = time.perf_counter()

    dt = (
        current_time
        - last_time
    )

    last_time = current_time

    if dt > 0.1:

        dt = 0.1


    # --------------------------------------------------
    # GAME
    # --------------------------------------------------

    if game_state == "PLAYING":

        with lock:

            direction1 = player_inputs[1]
            direction2 = player_inputs[2]


        # Player 1

        if direction1 == "up":

            game.player1.paddle.move_up(
                dt
            )

        elif direction1 == "down":

            game.player1.paddle.move_down(
                game.screen_height,
                dt
            )


        # Player 2

        if direction2 == "up":

            game.player2.paddle.move_up(
                dt
            )

        elif direction2 == "down":

            game.player2.paddle.move_down(
                game.screen_height,
                dt
            )


        # Update game

        game.update(
            dt
        )


        # --------------------------------------------------
        # POINT
        # --------------------------------------------------

        if game.last_point is not None:

            if game.last_point == 1:

                # Player 2 serves

                serving_player = 2

                game.ball.attach_to_paddle(
                    game.player2.paddle
                )

            elif game.last_point == 2:

                # Player 1 serves

                serving_player = 1

                game.ball.attach_to_paddle(
                    game.player1.paddle
                )

            game_state = "READY"

            print(
                f"Player {game.last_point} scored."
            )

            print(
                f"Player {serving_player} serves."
            )

            game.last_point = None


        # Send state

        send_state()


    # --------------------------------------------------
    # SERVER TICK
    # --------------------------------------------------

    time.sleep(
        1 / 60
    )
    