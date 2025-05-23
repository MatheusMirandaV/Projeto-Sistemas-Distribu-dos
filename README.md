# Descrição

Este projeto implementa uma simulação de rede social utilizando conceitos da matéria de Sistemas Distribuídos, com múltiplos servidores desenvolvidos em Java, Python e Node.js, além de clientes Python interativos.  
O sistema oferece as seguintes funcionalidades:

- Postagens
- Seguir e receber notificações
- Envio de mensagens privadas
- Replicação consistente entre servidores
- Eleição de coordenador (algoritmo Bully)
- Sincronização de relógio (algoritmo de Berkeley)
- Logs detalhados de todas as operações

---

## Funcionalidades

- **Postagens**  
  Usuários publicam mensagens visíveis para seus seguidores.

- **Seguir e receber notificações**  
  Usuários podem seguir outros; seguidores são notificados sempre que houver um post.

- **Mensagens privadas**  
  Envio e recebimento de mensagens privadas entre usuários.

- **Logs detalhados**  
  Cada servidor e cliente mantém seu próprio arquivo `.log`.

- **Replicação entre servidores**  
  Garantia de entrega das mensagens a todos servidores, mesmo os demais não sendo a porta na qual usuário está usando.

- **Eleição de coordenador**  
  Implementação do algoritmo Bully.

- **Sincronização de relógio**  
  Implementação do algoritmo de Berkeley.

---

## Requisitos

- **Python 3.x** (com `pyzmq`)  
- **Node.js** (com `zeromq`)  
- **Java 8+** (com `jeromq` e `gson`)  
- _(Opcional)_ Docker para facilitar execução/testes

---

## Instalação

1. **Clone o repositório**  
   ```bash
   git clone <URL_DO_SEU_REPOSITORIO>
   cd <NOME_DA_PASTA>
2. **Instale as dependências (Python, NodeJS, JAVA)**
   ```bash
   #Python
   pip install pyzmq
   #NodeJS
   npm install zeromq
   #No caso do JAVA baixe as libs jeromq e gson (coloque na mesma pasta ou configure seu CLASSPATH). 

## Como Executar

1. **Inicie os servidores**  
   - **Java**  
     ```bash
     javac -cp "jeromq-0.5.2.jar;gson-2.10.1.jar" Server1.java
     java -cp ".;jeromq-0.5.2.jar;gson-2.10.1.jar" Server1
     ```
   - **Python**  
     ```bash
     python server2.py
     ```
   - **Node.js**  
     ```bash
     node server3.js
     ```

2. **Inicie os clientes (usuários)**  
   ```bash
   python client_user.py 5551  # conecta no servidor Java
   python client_user.py 5552  # conecta no servidor Python
   python client_user.py 5553  # conecta no servidor Node.js
## Comandos Disponíveis (no cliente usuário)

- **`post`**  
  Publica uma mensagem.

- **`follow`**  
  Segue outro usuário (recebe notificações dos posts dele).

- **`pm`**  
  Envia mensagem privada para outro usuário.

- **`sair`**  
  Encerra a sessão do usuário.

---

## Comandos Especiais (no servidor)

- **`eleicao`**  
  Inicia o algoritmo Bully (eleição de coordenador).

- **`berkeley`**  
  _(Somente no coordenador)_ Inicia a sincronização de relógios pelo algoritmo de Berkeley.

## Exemplos de Teste

1. Faça login com dois usuários (ex: `U1` e `U2`), conectando cada um em um servidor diferente.  
2. Com `U2`, faça um `post`.
3. Com `U1`, use o comando `follow` e instrua para seguir `U2`.
4. Faça mais um `post` com `U2`; `U1` receberá uma notificação e ela estará registrada em `U1.log`.
5. Envie uma `mensagem privada` de `U2` para `U1`; ambos os logs serão atualizados.
6. No terminal do servidor, digite `eleicao` e observe a `eleição Bully` nos logs.
7. Digite `berkeley` no coordenador e veja a sincronização dos relógios.




