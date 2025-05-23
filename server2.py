import threading
import zmq
import logging
import json
import time
import random

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("server2.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# --- CONFIGS ---
SERVER_ID = 2
ALL_SERVER_IDS = [1, 2, 3]
current_coordinator = 3

feeds = {}
followers = {}
private_inbox = {}
notifications = {}
processed_ids = set()
lamport_clock = 0

local_clock = random.randint(10, 100)
berkeley_replies = {}

context = zmq.Context()

receiver = context.socket(zmq.PULL)
receiver.bind("tcp://*:5552")

replicator = context.socket(zmq.PUB)
replicator.bind("tcp://*:5562")

subscriber = context.socket(zmq.SUB)
subscriber.connect("tcp://localhost:5561")
subscriber.connect("tcp://localhost:5563")
subscriber.setsockopt_string(zmq.SUBSCRIBE, "")

pub_bully = context.socket(zmq.PUB)
pub_bully.bind("tcp://*:5572")

sub_bully = context.socket(zmq.SUB)
sub_bully.connect("tcp://localhost:5571")
sub_bully.connect("tcp://localhost:5573")
sub_bully.setsockopt_string(zmq.SUBSCRIBE, "")

# --- PUB para usuários (notificações) ---
user_pub = context.socket(zmq.PUB)
user_pub.bind("tcp://*:5582")

# --- FUNÇÕES DE NOTIFICAÇÃO ---

def notify_user(user_id, msg_type, content):
    payload = json.dumps({"type": msg_type, "content": content})
    user_pub.send_string(f"{user_id} {payload}")
    #logging.info(f"[NOTIFY_PUB] Notificou {user_id}: {content}")

def send_notification(user_id, content):
    notifications.setdefault(user_id, []).append(content)
    logging.info(f"[NOTIFICAÇÃO] {user_id} recebeu: {content}")
    notify_user(user_id, "notification", content)

def send_private_message(to_user, content, from_user=None):
    # Se quiser mostrar o remetente, inclua no conteúdo:
    if from_user:
        content = f"Mensagem privada de {from_user}: {content}"
    notify_user(to_user, "private_message", content)

def process_message(msg):
    global lamport_clock, current_coordinator
    try:
        data = json.loads(msg)
        id_evento = data.get("id_evento")
        if id_evento and id_evento in processed_ids:
            logging.info(f"Mensagem duplicada ignorada: {id_evento}")
            return
        if id_evento:
            processed_ids.add(id_evento)

        msg_clock = data.get("lamport_clock", 0)
        lamport_clock = max(lamport_clock, msg_clock) + 1
        logging.info(f"LAMPORT: {lamport_clock} (recebido: {msg_clock})")

        tipo = data.get("type")
        if tipo == "post":
            user = data["user_id"]
            content = data["content"]
            feeds.setdefault(user, []).append(content)
            logging.info(f"[POST] Novo post de {user}: {content}")

            segs = followers.get(user, [])
            for seguidor in segs:
                send_notification(seguidor, f"Novo post de {user}: {content}")

        elif tipo == "private_message":
            to_user = data["to"]
            from_user = data.get("from", None)
            content = data["content"]
            private_inbox.setdefault(to_user, []).append(content)
            logging.info(f"[PM] Mensagem privada para {to_user}: {content}")
            send_private_message(to_user, content, from_user=from_user)

        elif tipo == "follow":
            user = data["user_id"]
            to_follow = data["to_follow"]
            followers.setdefault(to_follow, []).append(user)
            logging.info(f"[FOLLOW] {user} agora segue {to_follow}!")
            # Notifica ambos
            send_notification(to_follow, f"{user} agora segue você!")
            send_notification(user, f"Você agora segue {to_follow}!")

        elif tipo == "ELECTION":
            sender_id = data["sender_id"]
            if SERVER_ID > sender_id:
                logging.info(f"[BULLY] Responde OK para eleição do {sender_id}")
                pub_bully.send_string(json.dumps({"type": "OK", "to": sender_id, "sender_id": SERVER_ID}))
                threading.Thread(target=start_election, daemon=True).start()
        elif tipo == "COORDINATOR":
            current_coordinator = data["coordinator_id"]
            logging.info(f"[BULLY] Novo coordenador reconhecido: {current_coordinator}")
        elif tipo == "OK":
            logging.info(f"[BULLY] Recebeu OK de {data['sender_id']} para eleição")
        elif tipo == "BERKELEY_REQUEST":
            handle_berkeley_request(data["sender_id"])
        elif tipo == "BERKELEY_REPLY":
            if data["to"] == SERVER_ID:
                handle_berkeley_reply(data["from"], data["clock"])
        elif tipo == "BERKELEY_ADJUST":
            if data["to"] == SERVER_ID:
                handle_berkeley_adjust(data["ajuste"])
        else:
            logging.info(f"Tipo de mensagem desconhecido: {tipo}")
    except Exception as e:
        logging.info(f"Erro ao processar mensagem: {e}")

# --- THREADS DE ASSINCRONIA ---
def replication_listener():
    while True:
        msg = subscriber.recv_string()
        process_message(msg)

def bully_listener():
    while True:
        msg = sub_bully.recv_string()
        process_message(msg)

def comando_loop():
    while True:
        cmd = input("Digite 'eleicao' para iniciar Bully, 'berkeley' para sincronizar relógio, ou Enter para continuar: ")
        if cmd.strip().lower() == "eleicao":
            start_election()
        elif cmd.strip().lower() == "berkeley" and current_coordinator == SERVER_ID:
            iniciar_berkeley()

def start_election():
    logging.info(f"[BULLY] Servidor {SERVER_ID} iniciou eleição!")
    for other_id in ALL_SERVER_IDS:
        if other_id > SERVER_ID:
            pub_bully.send_string(json.dumps({"type": "ELECTION", "sender_id": SERVER_ID}))
    time.sleep(2)
    global current_coordinator
    if current_coordinator != SERVER_ID:
        logging.info(f"[BULLY] {SERVER_ID} se anuncia como coordenador!")
        for other_id in ALL_SERVER_IDS:
            if other_id != SERVER_ID:
                pub_bully.send_string(json.dumps({"type": "COORDINATOR", "coordinator_id": SERVER_ID}))
        current_coordinator = SERVER_ID

def iniciar_berkeley():
    logging.info("[BERKELEY] Coordenador iniciou sincronização!")
    for other_id in ALL_SERVER_IDS:
        if other_id != SERVER_ID:
            pub_bully.send_string(json.dumps({
                "type": "BERKELEY_REQUEST",
                "sender_id": SERVER_ID
            }))
    berkeley_replies[SERVER_ID] = local_clock

def handle_berkeley_request(sender_id):
    logging.info(f"[BERKELEY] Recebeu solicitação de sincronização do coordenador {sender_id}")
    pub_bully.send_string(json.dumps({
        "type": "BERKELEY_REPLY",
        "to": sender_id,
        "from": SERVER_ID,
        "clock": local_clock
    }))

def handle_berkeley_reply(from_id, clock):
    berkeley_replies[from_id] = clock
    logging.info(f"[BERKELEY] Recebeu horário de {from_id}: {clock}")
    if len(berkeley_replies) == len(ALL_SERVER_IDS):
        media = int(sum(berkeley_replies.values()) / len(ALL_SERVER_IDS))
        logging.info(f"[BERKELEY] Média calculada: {media}")
        for target_id, clk in berkeley_replies.items():
            ajuste = media - clk
            pub_bully.send_string(json.dumps({
                "type": "BERKELEY_ADJUST",
                "to": target_id,
                "ajuste": ajuste
            }))
        berkeley_replies.clear()

def handle_berkeley_adjust(ajuste):
    global local_clock
    logging.info(f"[BERKELEY] Ajustando relógio em {ajuste} unidades (era {local_clock})")
    local_clock += ajuste
    logging.info(f"[BERKELEY] Novo valor do relógio: {local_clock}")

# --- INICIALIZA THREADS ---
threading.Thread(target=replication_listener, daemon=True).start()
threading.Thread(target=bully_listener, daemon=True).start()
threading.Thread(target=comando_loop, daemon=True).start()

logging.info("Servidor 2 (Python) iniciado")

while True:
    msg = receiver.recv_string()
    logging.info(f"[RECEBIDO USUÁRIO] {msg}")
    replicator.send_string(msg)
    process_message(msg)
