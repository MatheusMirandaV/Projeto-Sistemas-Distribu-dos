import zmq
import sys
import json
import uuid
import os
import threading
from datetime import datetime

ALL_USERS = ["U1", "U2", "U3", "U4", "U5"]

context = zmq.Context()
sender = context.socket(zmq.PUSH)

# Defina a porta do servidor que deseja testar
porta = sys.argv[1] if len(sys.argv) > 1 else "5552"
sender.connect(f"tcp://localhost:{porta}")

lamport_clock = 0  # Relógio lógico local do cliente

def log(msg, logfile):
    print(msg)
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def send_post(user_id, content, logfile):
    global lamport_clock
    lamport_clock += 1
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content_with_time = f"{content} | {timestamp}"
    msg = {
        "type": "post",
        "user_id": user_id,
        "id_evento": str(uuid.uuid4()),
        "lamport_clock": lamport_clock,
        "content": content_with_time
    }
    sender.send_string(json.dumps(msg))
    log(f"[POST] Lamport: {lamport_clock} | {user_id} postou: {content_with_time}", logfile)

def send_private(from_id, to_id, content, logfile):
    global lamport_clock
    lamport_clock += 1
    msg = {
        "type": "private_message",
        "from": from_id,
        "to": to_id,
        "id_evento": str(uuid.uuid4()),
        "lamport_clock": lamport_clock,
        "content": content
    }
    sender.send_string(json.dumps(msg))
    log(f"[PM ENVIADA] Lamport: {lamport_clock} | {from_id} para {to_id}: {content}", logfile)

def follow(user_id, to_follow, logfile):
    global lamport_clock
    lamport_clock += 1
    msg = {
        "type": "follow",
        "user_id": user_id,
        "to_follow": to_follow,
        "id_evento": str(uuid.uuid4()),
        "lamport_clock": lamport_clock
    }
    sender.send_string(json.dumps(msg))
    log(f"[FOLLOW] Lamport: {lamport_clock} | {user_id} seguiu {to_follow}", logfile)

def receive_loop(user_id, logfile):
    context = zmq.Context()
    sub = context.socket(zmq.SUB)
    sub.connect("tcp://localhost:5582")  # Python
    sub.connect("tcp://localhost:5581")  # Java
    sub.connect("tcp://localhost:5583")  # Node.js
    sub.setsockopt_string(zmq.SUBSCRIBE, user_id)
    while True:
        try:
            msg = sub.recv_string()
            if ' ' not in msg:
                continue
            _, payload = msg.split(' ', 1)
            try:
                data = json.loads(payload)
                if data.get("type") == "notification":
                    log(f"[NOTIFICAÇÃO RECEBIDA] {data['content']}", logfile)
                elif data.get("type") == "private_message":
                    log(f"[PM RECEBIDA] {data['content']}", logfile)
                #elif data.get("type") == "follow_ack":
                    #log(f"[NOTIFICAÇÃO RECEBIDA] {data['content']}", logfile)
                else:
                    log(f"[NOTIFICAÇÃO NÃO RECONHECIDA] {data}", logfile)
            except Exception as e:
                pass
        except Exception as e:
            pass


if __name__ == "__main__":
    # Verifica quais users já têm logs gerados
    used_users = [u for u in ALL_USERS if os.path.exists(f"{u}.log")]
    available_users = [u for u in ALL_USERS if u not in used_users]

    print("\n--- Simulador Interativo de Usuário Distribuído ---")
    if not available_users:
        print("Todos os user_ids já estão em uso nesta máquina! Saia de outra sessão para liberar um usuário.")
        sys.exit(1)
    print(f"Usuários disponíveis: {', '.join(available_users)}")
    user_id = input("Digite seu user_id: ").strip()
    if user_id not in available_users:
        print("User_id inválido ou já em uso. Saindo.")
        sys.exit(1)

    logfile = f"{user_id}.log"
    log(f"Usuário {user_id} iniciou sessão usando porta {porta}.", logfile)

    print(f"\nVocê é o usuário **{user_id}**. Outros usuários: {[u for u in ALL_USERS if u != user_id]}.\n")

    # Inicia thread de recebimento
    threading.Thread(target=receive_loop, args=(user_id, logfile), daemon=True).start()

    try:
        while True:
            op = input("Digite 'post', 'follow', 'pm' (mensagem privada), ou 'sair': ").strip().lower()
            if op == "sair":
                log(f"Usuário {user_id} encerrou sessão.", logfile)
                break
            if op == "post":
                conteudo = input("Conteúdo do post: ")
                send_post(user_id, conteudo, logfile)
            elif op == "follow":
                print(f"Usuários disponíveis para seguir: {[u for u in ALL_USERS if u != user_id]}")
                to_follow = input("Quem você quer seguir? (user_id): ").strip()
                if to_follow not in ALL_USERS or to_follow == user_id:
                    print("User_id inválido.")
                    continue
                follow(user_id, to_follow, logfile)
            elif op == "pm":
                print(f"Usuários disponíveis para enviar mensagem: {[u for u in ALL_USERS if u != user_id]}")
                to_id = input("Para quem? (user_id): ").strip()
                if to_id not in ALL_USERS or to_id == user_id:
                    print("User_id inválido.")
                    continue
                conteudo = input("Mensagem: ")
                send_private(user_id, to_id, conteudo, logfile)
            else:
                print("Opção inválida.")
            print("Mensagem enviada!\n")
    finally:
        pass
