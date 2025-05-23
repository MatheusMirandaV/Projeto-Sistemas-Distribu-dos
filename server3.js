const zmq = require('zeromq');
const readline = require('readline');
const receiver = new zmq.Pull;
const replicator = new zmq.Publisher;
const subscriber = new zmq.Subscriber;
const pubBully = new zmq.Publisher;
const subBully = new zmq.Subscriber;
const userPub = new zmq.Publisher; // <- novo para notificações

const fs = require('fs');
function log(msg) {
    console.log(msg);
    fs.appendFileSync('server3.log', msg + '\n');
}

const SERVER_ID = 3;
const ALL_SERVER_IDS = [1,2,3];
let currentCoordinator = 3;

const feeds = {};
const followers = {};
const privateInbox = {};
const notifications = {};
const processedIds = new Set();
let lamportClock = 0;

let localClock = Math.floor(Math.random() * 90) + 10;
let berkeleyReplies = {};

function notifyUser(userId, msgType, content) {
    const payload = JSON.stringify({type: msgType, content});
    userPub.send([Buffer.from(userId), Buffer.from(payload)]);
    //log(`[NOTIFY_PUB] Notificou ${userId}: ${content}`);
}

function sendNotification(userId, content) {
    if (!notifications[userId]) notifications[userId] = [];
    notifications[userId].push(content);
    log(`[Notificação registrada] ${userId} recebeu: ${content}`);
    notifyUser(userId, "notification", content);
}

function sendPrivateMessage(toUser, content, fromUser) {
    if (fromUser) {
        content = `Mensagem privada de ${fromUser}: ${content}`;
    }
    notifyUser(toUser, "private_message", content);
}

async function processMessage(msg) {
    try {
        const data = JSON.parse(msg.toString());
        const idEvento = data.id_evento;
        if (idEvento && processedIds.has(idEvento)) {
            log("Mensagem duplicada ignorada: " + idEvento);
            return;
        }
        if (idEvento) processedIds.add(idEvento);

        const msgClock = data.lamport_clock || 0;
        lamportClock = Math.max(lamportClock, msgClock) + 1;
        log(`LAMPORT: ${lamportClock} (recebido: ${msgClock})`);

        const tipo = data.type;

        if (tipo === "post") {
            const user = data.user_id;
            const content = data.content;
            if (!feeds[user]) feeds[user] = [];
            feeds[user].push(content);
            log(`[POST] Novo post de ${user}: ${content}`);
            const segs = followers[user] || [];
            for (const seguidor of segs) {
                sendNotification(seguidor, `Novo post de ${user}: ${content}`);
            }
        } else if (tipo === "private_message") {
            const toUser = data.to;
            const fromUser = data.from || null;
            const content = data.content;
            if (!privateInbox[toUser]) privateInbox[toUser] = [];
            privateInbox[toUser].push(content);
            log(`[PM] Mensagem privada para ${toUser}: ${content}`);
            sendPrivateMessage(toUser, content, fromUser);
        } else if (tipo === "follow") {
            const user = data.user_id;
            const toFollow = data.to_follow;
            if (!followers[toFollow]) followers[toFollow] = [];
            followers[toFollow].push(user);
            log(`[FOLLOW] ${user} agora segue ${toFollow}!`);
            // Notifica ambos
            sendNotification(toFollow, `${user} agora segue você!`);
            sendNotification(user, `Você agora segue ${toFollow}!`);
        } else if (tipo === "ELECTION") {
            const sender_id = data.sender_id;
            if (SERVER_ID > sender_id) {
                log(`[BULLY] Responde OK para eleição do ${sender_id}`);
                pubBully.send(JSON.stringify({type: "OK", to: sender_id, sender_id: SERVER_ID}));
                setTimeout(startElection, 100);
            }
        } else if (tipo === "COORDINATOR") {
            currentCoordinator = data.coordinator_id;
            log(`[BULLY] Novo coordenador reconhecido: ${currentCoordinator}`);
        } else if (tipo === "OK") {
            log(`[BULLY] Recebeu OK de ${data.sender_id} para eleição`);
        }
        // --- BERKELEY ---
        else if (tipo === "BERKELEY_REQUEST") {
            handleBerkeleyRequest(data.sender_id);
        } else if (tipo === "BERKELEY_REPLY") {
            if (data.to === SERVER_ID) handleBerkeleyReply(data.from, data.clock);
        } else if (tipo === "BERKELEY_ADJUST") {
            if (data.to === SERVER_ID) handleBerkeleyAdjust(data.ajuste);
        } else {
            log("Tipo de mensagem desconhecido: " + tipo);
        }
    } catch (err) {
        log("Erro ao processar mensagem: " + err);
    }
}

async function run() {
    await receiver.bind('tcp://*:5553');
    await replicator.bind('tcp://*:5563');

    subscriber.connect('tcp://localhost:5561');
    subscriber.connect('tcp://localhost:5562');
    subscriber.subscribe();

    await pubBully.bind('tcp://*:5573');
    subBully.connect('tcp://localhost:5571');
    subBully.connect('tcp://localhost:5572');
    subBully.subscribe();

    // --- Novo PUB para usuários (porta 5583)
    await userPub.bind('tcp://*:5583');

    (async () => {
        for await (const [msg] of subscriber) await processMessage(msg);
    })();
    (async () => {
        for await (const [msg] of subBully) await processMessage(msg);
    })();

    log("Servidor 3 (Node.js) iniciado com sucesso.");

    // Comando interativo para eleição/sincronização
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.on('line', (line) => {
        if (line.trim().toLowerCase() === 'eleicao') startElection();
        if (line.trim().toLowerCase() === 'berkeley' && currentCoordinator === SERVER_ID) iniciarBerkeley();
    });

    for await (const [msg] of receiver) {
        await replicator.send(msg);
        await processMessage(msg);
    }
}

// --- BULLY ---
function startElection() {
    log(`[BULLY] Servidor ${SERVER_ID} iniciou eleição!`);
    for (let other_id of ALL_SERVER_IDS) {
        if (other_id > SERVER_ID) {
            pubBully.send(JSON.stringify({type: "ELECTION", sender_id: SERVER_ID}));
        }
    }
    setTimeout(() => {
        if (currentCoordinator !== SERVER_ID) {
            log(`[BULLY] ${SERVER_ID} se anuncia como coordenador!`);
            for (let other_id of ALL_SERVER_IDS) {
                if (other_id !== SERVER_ID) {
                    pubBully.send(JSON.stringify({type: "COORDINATOR", coordinator_id: SERVER_ID}));
                }
            }
            currentCoordinator = SERVER_ID;
        }
    }, 2000);
}

// --- BERKELEY ---
function iniciarBerkeley() {
    log("[BERKELEY] Coordenador iniciou sincronização!");
    for (let other_id of ALL_SERVER_IDS) {
        if (other_id !== SERVER_ID) {
            pubBully.send(JSON.stringify({
                type: "BERKELEY_REQUEST",
                sender_id: SERVER_ID
            }));
        }
    }
    berkeleyReplies[SERVER_ID] = localClock;
}

function handleBerkeleyRequest(sender_id) {
    log(`[BERKELEY] Recebeu solicitação de sincronização do coordenador ${sender_id}`);
    pubBully.send(JSON.stringify({
        type: "BERKELEY_REPLY",
        to: sender_id,
        from: SERVER_ID,
        clock: localClock
    }));
}

function handleBerkeleyReply(from_id, clock) {
    berkeleyReplies[from_id] = clock;
    log(`[BERKELEY] Recebeu horário de ${from_id}: ${clock}`);
    if (Object.keys(berkeleyReplies).length === ALL_SERVER_IDS.length) {
        let values = Object.values(berkeleyReplies);
        let media = Math.round(values.reduce((a, b) => a + b, 0) / values.length);
        log(`[BERKELEY] Média calculada: ${media}`);
        for (let target_id in berkeleyReplies) {
            let ajuste = media - berkeleyReplies[target_id];
            pubBully.send(JSON.stringify({
                type: "BERKELEY_ADJUST",
                to: Number(target_id),
                ajuste
            }));
        }
        berkeleyReplies = {};
    }
}

function handleBerkeleyAdjust(ajuste) {
    log(`[BERKELEY] Ajustando relógio em ${ajuste} unidades (era ${localClock})`);
    localClock += ajuste;
    log(`[BERKELEY] Novo valor do relógio: ${localClock}`);
}

// Start everything!
run();
