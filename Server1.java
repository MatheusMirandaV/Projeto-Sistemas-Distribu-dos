import org.zeromq.ZMQ;
import org.zeromq.SocketType;
import com.google.gson.*;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.io.FileWriter;
import java.io.IOException;

public class Server1 {
    private static final int SERVER_ID = 1;
    private static final List<Integer> ALL_SERVER_IDS = Arrays.asList(1,2,3);
    private static int currentCoordinator = 3;

    private static Map<String, List<String>> feeds = new HashMap<>();
    private static Map<String, List<String>> followers = new HashMap<>();
    private static Map<String, List<String>> privateInbox = new HashMap<>();
    private static Map<String, List<String>> notifications = new HashMap<>();
    private static Set<String> processedIds = new HashSet<>();
    private static int lamportClock = 0;

    // Berkeley clock simulation
    private static int localClock = new Random().nextInt(90) + 10;
    private static Map<Integer, Integer> berkeleyReplies = new HashMap<>();

    private static FileWriter fw;
    static {
        try {
            fw = new FileWriter("server1.log", true);
        } catch (IOException e) { e.printStackTrace(); }
    }
    public static void log(String msg) {
        System.out.println(msg);
        try {
            fw.write(msg + "\n");
            fw.flush();
        } catch (IOException e) {
            System.out.println("Erro ao escrever no arquivo de log: " + e.getMessage());
            e.printStackTrace();
        }
    }

    // --- Novo: Notifica usuário via PUB (ZeroMQ)
    public static void notifyUser(ZMQ.Socket userPub, String userId, String type, String content) {
        JsonObject payload = new JsonObject();
        payload.addProperty("type", type);
        payload.addProperty("content", content);
        String mensagem = userId + " " + payload.toString();
        userPub.send(mensagem);
        //log("[NOTIFY_PUB] Notificou " + userId + ": " + content);
    }

    public static void sendNotification(String userId, String content, ZMQ.Socket userPub) {
        notifications.computeIfAbsent(userId, k -> new ArrayList<>()).add(content);
        log("[Notificação registrada] " + userId + " recebeu: " + content);
        notifyUser(userPub, userId, "notification", content);
    }

    public static void sendPrivateMessage(String toUser, String content, ZMQ.Socket userPub) {
        notifyUser(userPub, toUser, "private_message", content);
    }

    public static void main(String[] args) {
        log("Servidor 1 (Java) iniciou corretamente.");
        Gson gson = new Gson();
        ZMQ.Context context = ZMQ.context(1);

        ZMQ.Socket receiver = context.socket(SocketType.PULL);
        receiver.bind("tcp://*:5551");

        ZMQ.Socket replicator = context.socket(SocketType.PUB);
        replicator.bind("tcp://*:5561");

        ZMQ.Socket subscriber = context.socket(SocketType.SUB);
        subscriber.connect("tcp://localhost:5562");
        subscriber.connect("tcp://localhost:5563");
        subscriber.subscribe("".getBytes());

        ZMQ.Socket pubBully = context.socket(SocketType.PUB);
        pubBully.bind("tcp://*:5571");

        ZMQ.Socket subBully = context.socket(SocketType.SUB);
        subBully.connect("tcp://localhost:5572");
        subBully.connect("tcp://localhost:5573");
        subBully.subscribe("".getBytes());

        // --- Novo: PUB de notificações para usuários
        ZMQ.Socket userPub = context.socket(SocketType.PUB);
        userPub.bind("tcp://*:5581");

        ExecutorService executor = Executors.newFixedThreadPool(5);

        executor.submit(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                String replicatedMsg = subscriber.recvStr(0);
                processMessage(gson, replicatedMsg, pubBully, userPub);
            }
        });
        executor.submit(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                String bullyMsg = subBully.recvStr(0);
                processMessage(gson, bullyMsg, pubBully, userPub);
            }
        });
        executor.submit(() -> {
            Scanner sc = new Scanner(System.in);
            while (true) {
                System.out.print("Digite 'eleicao' para Bully, 'berkeley' para sincronizar relógio, ou Enter para continuar: ");
                String cmd = sc.nextLine();
                if (cmd.equalsIgnoreCase("eleicao")) {
                    startElection(pubBully);
                }
                if (cmd.equalsIgnoreCase("berkeley") && currentCoordinator == SERVER_ID) {
                    iniciarBerkeley(pubBully);
                }
            }
        });

        ZMQ.Poller poller = context.poller(1);
        poller.register(receiver, ZMQ.Poller.POLLIN);
        while (!Thread.currentThread().isInterrupted()) {
            int events = poller.poll(100);
            if (events > 0 && poller.pollin(0)) {
                String msg = receiver.recvStr(0);
                replicator.send(msg);
                processMessage(gson, msg, pubBully, userPub);
            }
        }
    }

    private static void processMessage(Gson gson, String msg, ZMQ.Socket pubBully, ZMQ.Socket userPub) {
        try {
            JsonObject data = gson.fromJson(msg, JsonObject.class);
            String idEvento = data.has("id_evento") ? data.get("id_evento").getAsString() : null;
            if (idEvento != null && processedIds.contains(idEvento)) {
                log("Mensagem duplicada ignorada: " + idEvento);
                return;
            }
            if (idEvento != null) processedIds.add(idEvento);

            int msgClock = data.has("lamport_clock") ? data.get("lamport_clock").getAsInt() : 0;
            lamportClock = Math.max(lamportClock, msgClock) + 1;
            log("LAMPORT: " + lamportClock + " (recebido: " + msgClock + ")");

            String tipo = data.has("type") ? data.get("type").getAsString() : "";

            if (tipo.equals("post")) {
                String user = data.get("user_id").getAsString();
                String content = data.get("content").getAsString();
                feeds.computeIfAbsent(user, k -> new ArrayList<>()).add(content);
                log("Novo post de " + user + ": " + content);

                List<String> segs = followers.getOrDefault(user, new ArrayList<>());
                for (String seguidor : segs) {
                    sendNotification(seguidor, "Novo post de " + user + ": " + content, userPub);
                }
            } else if (tipo.equals("private_message")) {
                String toUser = data.get("to").getAsString();
                String content = data.get("content").getAsString();
                privateInbox.computeIfAbsent(toUser, k -> new ArrayList<>()).add(content);
                log("Mensagem privada para " + toUser + ": " + content);
                sendPrivateMessage(toUser, "Mensagem privada de " + data.get("from").getAsString() + ": " + content, userPub);
            } else if (tipo.equals("follow")) {
                String user = data.get("user_id").getAsString();
                String toFollow = data.get("to_follow").getAsString();
                followers.computeIfAbsent(toFollow, k -> new ArrayList<>()).add(user);
                log(user + " agora segue " + toFollow + "!");
                // Opcional: notifique ambos, se quiser!
                sendNotification(toFollow, user + " agora segue você!", userPub);
                sendNotification(user, "Você agora segue " + toFollow + "!", userPub);
            }
            // ... (restante: eleição, Berkeley etc. igual antes) ...
            else if (tipo.equals("ELECTION")) {
                int senderId = data.get("sender_id").getAsInt();
                if (SERVER_ID > senderId) {
                    log("[BULLY] Responde OK para eleição do " + senderId);
                    JsonObject response = new JsonObject();
                    response.addProperty("type", "OK");
                    response.addProperty("to", senderId);
                    response.addProperty("sender_id", SERVER_ID);
                    pubBully.send(response.toString());
                }
            } else if (tipo.equals("COORDINATOR")) {
                currentCoordinator = data.get("coordinator_id").getAsInt();
                log("[BULLY] Novo coordenador reconhecido: " + currentCoordinator);
            } else if (tipo.equals("OK")) {
                log("[BULLY] Recebeu OK de " + data.get("sender_id").getAsInt() + " para eleição");
            } else if (tipo.equals("BERKELEY_REQUEST")) {
                int senderId = data.get("sender_id").getAsInt();
                handleBerkeleyRequest(pubBully, senderId);
            } else if (tipo.equals("BERKELEY_REPLY")) {
                int toId = data.get("to").getAsInt();
                int fromId = data.get("from").getAsInt();
                int clock = data.get("clock").getAsInt();
                if (toId == SERVER_ID) {
                    handleBerkeleyReply(pubBully, fromId, clock);
                }
            } else if (tipo.equals("BERKELEY_ADJUST")) {
                int toId = data.get("to").getAsInt();
                int ajuste = data.get("ajuste").getAsInt();
                if (toId == SERVER_ID) {
                    handleBerkeleyAdjust(ajuste);
                }
            }
        } catch (Exception e) {
            log("Erro ao processar mensagem: " + e.getMessage());
        }
    }

    // --- BULLY --- (igual antes)
    public static void startElection(ZMQ.Socket pubBully) {
        log("[BULLY] Servidor " + SERVER_ID + " iniciou eleição!");
        for (int otherId : ALL_SERVER_IDS) {
            if (otherId > SERVER_ID) {
                JsonObject msg = new JsonObject();
                msg.addProperty("type", "ELECTION");
                msg.addProperty("sender_id", SERVER_ID);
                pubBully.send(msg.toString());
            }
        }
        try { Thread.sleep(2000); } catch (Exception e) {}
        if (currentCoordinator != SERVER_ID) {
            log("[BULLY] " + SERVER_ID + " se anuncia como coordenador!");
            for (int otherId : ALL_SERVER_IDS) {
                if (otherId != SERVER_ID) {
                    JsonObject msg = new JsonObject();
                    msg.addProperty("type", "COORDINATOR");
                    msg.addProperty("coordinator_id", SERVER_ID);
                    pubBully.send(msg.toString());
                }
            }
            currentCoordinator = SERVER_ID;
        }
    }
    // ... (Berkeley handlers igual antes) ...
    public static void iniciarBerkeley(ZMQ.Socket pubBully) {
        log("[BERKELEY] Coordenador iniciou sincronização!");
        for (int otherId : ALL_SERVER_IDS) {
            if (otherId != SERVER_ID) {
                JsonObject req = new JsonObject();
                req.addProperty("type", "BERKELEY_REQUEST");
                req.addProperty("sender_id", SERVER_ID);
                pubBully.send(req.toString());
            }
        }
        berkeleyReplies.put(SERVER_ID, localClock);
    }
    public static void handleBerkeleyRequest(ZMQ.Socket pubBully, int senderId) {
        log("[BERKELEY] Recebeu solicitação de sincronização do coordenador " + senderId);
        JsonObject reply = new JsonObject();
        reply.addProperty("type", "BERKELEY_REPLY");
        reply.addProperty("to", senderId);
        reply.addProperty("from", SERVER_ID);
        reply.addProperty("clock", localClock);
        pubBully.send(reply.toString());
    }
    public static void handleBerkeleyReply(ZMQ.Socket pubBully, int fromId, int clock) {
        berkeleyReplies.put(fromId, clock);
        log("[BERKELEY] Recebeu horário de " + fromId + ": " + clock);
        if (berkeleyReplies.size() == ALL_SERVER_IDS.size()) {
            int media = (int) berkeleyReplies.values().stream().mapToInt(i -> i).average().orElse(localClock);
            log("[BERKELEY] Média calculada: " + media);
            for (Map.Entry<Integer, Integer> entry : berkeleyReplies.entrySet()) {
                int ajuste = media - entry.getValue();
                JsonObject adjust = new JsonObject();
                adjust.addProperty("type", "BERKELEY_ADJUST");
                adjust.addProperty("to", entry.getKey());
                adjust.addProperty("ajuste", ajuste);
                pubBully.send(adjust.toString());
            }
            berkeleyReplies.clear();
        }
    }
    public static void handleBerkeleyAdjust(int ajuste) {
        log("[BERKELEY] Ajustando relógio em " + ajuste + " unidades (era " + localClock + ")");
        localClock += ajuste;
        log("[BERKELEY] Novo valor do relógio: " + localClock);
    }
}
