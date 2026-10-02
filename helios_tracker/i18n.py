"""The mod's in-game text - its options in the mod menu, the updater's boxes and messages - in the game's language
(Core.Object's GetLanguage, read once at load: no setting of ours), the page's nine languages, English otherwise.
The page has its own catalogs (web/i18n/*.js); these are the in-game ones, same languages. Logs stay English.

t("key", name=value) -> the text, {name} filled. Every language has every key (offline_check).
No SDK imports: the language comes in through set_game_language().
"""

GAME_LANGS = {"INT": "en", "FRA": "fr", "DEU": "de", "ITA": "it", "ESN": "es", "JPN": "ja", "KOR": "ko", "TWN": "zh",
              "RUS": "ru"}  # (web/js/i18n.js's GAME_LANGS)

TEXT: dict[str, dict[str, str]] = {
    "en": {
        "mod.desc": "A live map of the current level in your web browser: the game's map with players, enemies, NPCs,"
                    " vehicles and loot on it, with zoom and pan.",
        "open.name": "Open Map in Browser",
        "open.desc": "Opens the live map in your default browser (the mod must be enabled).",
        "port.name": "Port",
        "port.desc": "Port of the local web server: the page is at http://localhost:<port>/. Applied when you leave"
                     " this menu.",
        "lan.name": "Allow LAN Access",
        "lan.desc": "Also serve the map to other devices on your network (a phone, a tablet, another PC). Windows may"
                    " ask to let the game through its firewall. Off: only this PC can open it.",
        "rate.name": "Tick Rate",
        "rate.desc": "How many times per second the mod reads the game and sends it to the page (the page smooths"
                     " movement in between). Lower: lighter on the game and on your upload when sharing the map.",
        "auto.name": "Automatic Updates",
        "auto.desc": "Once a day, looks for a new version of Helios Tracker on GitHub, installs it and reloads the mod"
                     " with it. Off: only when you press Check for Updates.",
        "check.name": "Check for Updates",
        "check.desc": "Looks for a new version of Helios Tracker now, and asks before installing it.",
        "box.title": "Helios Tracker",
        "box.updateTitle": "Helios Tracker Update",
        "update.checking": "Checking for updates...",
        "update.downloading": "Downloading Helios Tracker {tag}...",
        "update.cancel": "Cancel",
        "update.available": "Helios Tracker {tag} is available (you have {ours}).",
        "update.download": "Download and Install",
        "update.notNow": "Not Now",
        "update.installFailed": "{tag} couldn't be installed:\n{error}",
        "update.ok": "OK",
        "update.installed": "Helios Tracker {tag} is installed: it runs from the next game start (this session runs"
                            " {ours}).",
        "update.reloadNow": "Reload Now",
        "update.later": "Later",
        "update.latest": "You have the latest version ({ours}).",
        "update.checkFailed": "Couldn't check for updates:\n{error}",
        "update.updated": "Helios Tracker updated to {tag}",
        "update.unknownVersion": "an unknown version",
    },
    "fr": {
        "mod.desc": "Une carte en direct du niveau en cours dans votre navigateur : la carte du jeu avec les joueurs, les"
                    " ennemis, les PNJ, les véhicules et le butin, avec zoom et déplacement.",
        "open.name": "Ouvrir la carte dans le navigateur",
        "open.desc": "Ouvre la carte en direct dans votre navigateur par défaut (le mod doit être activé).",
        "port.name": "Port",
        "port.desc": "Port du serveur web local : la page est à http://localhost:<port>/. Appliqué en quittant ce menu.",
        "lan.name": "Autoriser l'accès réseau local",
        "lan.desc": "Sert aussi la carte aux autres appareils de votre réseau (un téléphone, une tablette, un autre PC)."
                    " Windows peut demander d'autoriser le jeu dans son pare-feu. Désactivé : seul ce PC peut l'ouvrir.",
        "rate.name": "Fréquence de lecture",
        "rate.desc": "Combien de fois par seconde le mod lit le jeu et l'envoie à la page (la page lisse les mouvements"
                     " entre deux). Plus bas : plus léger pour le jeu et pour votre envoi quand vous partagez la carte.",
        "auto.name": "Mises à jour automatiques",
        "auto.desc": "Une fois par jour, cherche une nouvelle version de Helios Tracker sur GitHub, l'installe et"
                     " recharge le mod avec. Désactivé : seulement quand vous appuyez sur Rechercher des mises à jour.",
        "check.name": "Rechercher des mises à jour",
        "check.desc": "Cherche maintenant une nouvelle version de Helios Tracker, et demande avant de l'installer.",
        "box.title": "Helios Tracker",
        "box.updateTitle": "Mise à jour de Helios Tracker",
        "update.checking": "Recherche de mises à jour...",
        "update.downloading": "Téléchargement de Helios Tracker {tag}...",
        "update.cancel": "Annuler",
        "update.available": "Helios Tracker {tag} est disponible (vous avez {ours}).",
        "update.download": "Télécharger et installer",
        "update.notNow": "Pas maintenant",
        "update.installFailed": "{tag} n'a pas pu être installé :\n{error}",
        "update.ok": "OK",
        "update.installed": "Helios Tracker {tag} est installé : il sera utilisé au prochain lancement du jeu (cette"
                            " session utilise {ours}).",
        "update.reloadNow": "Recharger maintenant",
        "update.later": "Plus tard",
        "update.latest": "Vous avez la dernière version ({ours}).",
        "update.checkFailed": "Impossible de rechercher les mises à jour :\n{error}",
        "update.updated": "Helios Tracker mis à jour en {tag}",
        "update.unknownVersion": "une version inconnue",
    },
    "de": {
        "mod.desc": "Eine Live-Karte des aktuellen Levels in deinem Browser: die Karte des Spiels mit Spielern, Gegnern,"
                    " NPCs, Fahrzeugen und Beute, mit Zoom und Verschieben.",
        "open.name": "Karte im Browser öffnen",
        "open.desc": "Öffnet die Live-Karte in deinem Standardbrowser (die Mod muss aktiviert sein).",
        "port.name": "Port",
        "port.desc": "Port des lokalen Webservers: die Seite ist unter http://localhost:<port>/. Wird beim Verlassen"
                     " dieses Menüs übernommen.",
        "lan.name": "LAN-Zugriff erlauben",
        "lan.desc": "Stellt die Karte auch anderen Geräten in deinem Netzwerk bereit (Handy, Tablet, anderer PC)."
                    " Windows fragt eventuell, ob das Spiel durch die Firewall darf. Aus: nur dieser PC kann sie öffnen.",
        "rate.name": "Abfragerate",
        "rate.desc": "Wie oft pro Sekunde die Mod das Spiel ausliest und an die Seite sendet (die Seite glättet die"
                     " Bewegung dazwischen). Niedriger: schont das Spiel und deinen Upload, wenn du die Karte teilst.",
        "auto.name": "Automatische Updates",
        "auto.desc": "Sucht einmal am Tag auf GitHub nach einer neuen Version von Helios Tracker, installiert sie und"
                     " lädt die Mod damit neu. Aus: nur wenn du Nach Updates suchen drückst.",
        "check.name": "Nach Updates suchen",
        "check.desc": "Sucht jetzt nach einer neuen Version von Helios Tracker und fragt vor der Installation.",
        "box.title": "Helios Tracker",
        "box.updateTitle": "Helios Tracker-Update",
        "update.checking": "Suche nach Updates...",
        "update.downloading": "Helios Tracker {tag} wird heruntergeladen...",
        "update.cancel": "Abbrechen",
        "update.available": "Helios Tracker {tag} ist verfügbar (du hast {ours}).",
        "update.download": "Herunterladen und installieren",
        "update.notNow": "Nicht jetzt",
        "update.installFailed": "{tag} konnte nicht installiert werden:\n{error}",
        "update.ok": "OK",
        "update.installed": "Helios Tracker {tag} ist installiert: ab dem nächsten Spielstart aktiv (diese Sitzung"
                            " läuft mit {ours}).",
        "update.reloadNow": "Jetzt neu laden",
        "update.later": "Später",
        "update.latest": "Du hast die neueste Version ({ours}).",
        "update.checkFailed": "Suche nach Updates fehlgeschlagen:\n{error}",
        "update.updated": "Helios Tracker auf {tag} aktualisiert",
        "update.unknownVersion": "eine unbekannte Version",
    },
    "it": {
        "mod.desc": "Una mappa in tempo reale del livello attuale nel tuo browser: la mappa del gioco con giocatori,"
                    " nemici, PNG, veicoli e bottino, con zoom e spostamento.",
        "open.name": "Apri la mappa nel browser",
        "open.desc": "Apre la mappa in tempo reale nel browser predefinito (la mod deve essere attiva).",
        "port.name": "Porta",
        "port.desc": "Porta del server web locale: la pagina è su http://localhost:<port>/. Applicata quando esci da"
                     " questo menu.",
        "lan.name": "Consenti accesso LAN",
        "lan.desc": "Mostra la mappa anche agli altri dispositivi della tua rete (telefono, tablet, un altro PC). Windows"
                    " potrebbe chiedere di consentire il gioco nel firewall. Disattivato: solo questo PC può aprirla.",
        "rate.name": "Frequenza di lettura",
        "rate.desc": "Quante volte al secondo la mod legge il gioco e lo invia alla pagina (la pagina rende fluido il"
                     " movimento nel mezzo). Più bassa: più leggera per il gioco e per il tuo upload quando condividi la"
                     " mappa.",
        "auto.name": "Aggiornamenti automatici",
        "auto.desc": "Una volta al giorno cerca una nuova versione di Helios Tracker su GitHub, la installa e ricarica"
                     " la mod. Disattivato: solo quando premi Cerca aggiornamenti.",
        "check.name": "Cerca aggiornamenti",
        "check.desc": "Cerca ora una nuova versione di Helios Tracker e chiede prima di installarla.",
        "box.title": "Helios Tracker",
        "box.updateTitle": "Aggiornamento di Helios Tracker",
        "update.checking": "Ricerca aggiornamenti...",
        "update.downloading": "Download di Helios Tracker {tag}...",
        "update.cancel": "Annulla",
        "update.available": "Helios Tracker {tag} è disponibile (hai {ours}).",
        "update.download": "Scarica e installa",
        "update.notNow": "Non ora",
        "update.installFailed": "Impossibile installare {tag}:\n{error}",
        "update.ok": "OK",
        "update.installed": "Helios Tracker {tag} è installato: sarà usato dal prossimo avvio del gioco (questa sessione"
                            " usa {ours}).",
        "update.reloadNow": "Ricarica ora",
        "update.later": "Più tardi",
        "update.latest": "Hai l'ultima versione ({ours}).",
        "update.checkFailed": "Impossibile cercare aggiornamenti:\n{error}",
        "update.updated": "Helios Tracker aggiornato a {tag}",
        "update.unknownVersion": "una versione sconosciuta",
    },
    "es": {
        "mod.desc": "Un mapa en directo del nivel actual en tu navegador: el mapa del juego con jugadores, enemigos, PNJ,"
                    " vehículos y botín, con zoom y desplazamiento.",
        "open.name": "Abrir mapa en el navegador",
        "open.desc": "Abre el mapa en directo en tu navegador predeterminado (el mod debe estar activado).",
        "port.name": "Puerto",
        "port.desc": "Puerto del servidor web local: la página está en http://localhost:<port>/. Se aplica al salir de"
                     " este menú.",
        "lan.name": "Permitir acceso LAN",
        "lan.desc": "También sirve el mapa a otros dispositivos de tu red (un móvil, una tableta, otro PC). Windows puede"
                    " pedir permiso para el juego en su cortafuegos. Desactivado: solo este PC puede abrirlo.",
        "rate.name": "Frecuencia de lectura",
        "rate.desc": "Cuántas veces por segundo el mod lee el juego y lo envía a la página (la página suaviza el"
                     " movimiento entre medias). Más baja: más ligera para el juego y para tu subida al compartir el"
                     " mapa.",
        "auto.name": "Actualizaciones automáticas",
        "auto.desc": "Una vez al día busca una nueva versión de Helios Tracker en GitHub, la instala y recarga el mod"
                     " con ella. Desactivado: solo cuando pulses Buscar actualizaciones.",
        "check.name": "Buscar actualizaciones",
        "check.desc": "Busca ahora una nueva versión de Helios Tracker y pregunta antes de instalarla.",
        "box.title": "Helios Tracker",
        "box.updateTitle": "Actualización de Helios Tracker",
        "update.checking": "Buscando actualizaciones...",
        "update.downloading": "Descargando Helios Tracker {tag}...",
        "update.cancel": "Cancelar",
        "update.available": "Helios Tracker {tag} está disponible (tienes {ours}).",
        "update.download": "Descargar e instalar",
        "update.notNow": "Ahora no",
        "update.installFailed": "No se pudo instalar {tag}:\n{error}",
        "update.ok": "Aceptar",
        "update.installed": "Helios Tracker {tag} está instalado: se usará desde el próximo inicio del juego (esta sesión"
                            " usa {ours}).",
        "update.reloadNow": "Recargar ahora",
        "update.later": "Más tarde",
        "update.latest": "Tienes la última versión ({ours}).",
        "update.checkFailed": "No se pudieron buscar actualizaciones:\n{error}",
        "update.updated": "Helios Tracker actualizado a {tag}",
        "update.unknownVersion": "una versión desconocida",
    },
    "ja": {
        "mod.desc": "現在のレベルのライブマップをWebブラウザに表示します：ゲームのマップにプレイヤー、敵、NPC、乗り物、"
                    "戦利品を表示し、ズームと移動ができます。",
        "open.name": "ブラウザでマップを開く",
        "open.desc": "既定のブラウザでライブマップを開きます（Modが有効になっている必要があります）。",
        "port.name": "ポート",
        "port.desc": "ローカルWebサーバーのポート：ページは http://localhost:<port>/ にあります。このメニューを閉じると適用されます。",
        "lan.name": "LANアクセスを許可",
        "lan.desc": "ネットワーク上の他の機器（スマホ、タブレット、別のPC）にもマップを配信します。Windowsがファイアウォールで"
                    "ゲームの許可を求めることがあります。オフ：このPCだけが開けます。",
        "rate.name": "読み取り頻度",
        "rate.desc": "Modが1秒間にゲームを読み取ってページに送る回数（ページがその間の動きを滑らかにします）。低いほど"
                     "ゲームの負荷と、マップ共有時のアップロードが軽くなります。",
        "auto.name": "自動アップデート",
        "auto.desc": "1日に1回GitHubでHelios Trackerの新しいバージョンを探し、インストールしてModを再読み込みします。"
                     "オフ：「アップデートを確認」を押したときだけ。",
        "check.name": "アップデートを確認",
        "check.desc": "今すぐHelios Trackerの新しいバージョンを探し、インストール前に確認します。",
        "box.title": "Helios Tracker",
        "box.updateTitle": "Helios Tracker のアップデート",
        "update.checking": "アップデートを確認中...",
        "update.downloading": "Helios Tracker {tag} をダウンロード中...",
        "update.cancel": "キャンセル",
        "update.available": "Helios Tracker {tag} が利用できます（現在 {ours}）。",
        "update.download": "ダウンロードしてインストール",
        "update.notNow": "今はしない",
        "update.installFailed": "{tag} をインストールできませんでした：\n{error}",
        "update.ok": "OK",
        "update.installed": "Helios Tracker {tag} をインストールしました：次回のゲーム起動から使われます（このセッションは {ours}）。",
        "update.reloadNow": "今すぐ再読み込み",
        "update.later": "後で",
        "update.latest": "最新バージョンです（{ours}）。",
        "update.checkFailed": "アップデートを確認できませんでした：\n{error}",
        "update.updated": "Helios Tracker を {tag} に更新しました",
        "update.unknownVersion": "不明なバージョン",
    },
    "ko": {
        "mod.desc": "현재 레벨의 실시간 지도를 웹 브라우저에 표시합니다: 게임 지도 위에 플레이어, 적, NPC, 차량, 전리품을"
                    " 보여 주며 확대와 이동이 가능합니다.",
        "open.name": "브라우저에서 지도 열기",
        "open.desc": "기본 브라우저에서 실시간 지도를 엽니다(모드가 활성화되어 있어야 합니다).",
        "port.name": "포트",
        "port.desc": "로컬 웹 서버의 포트: 페이지 주소는 http://localhost:<port>/ 입니다. 이 메뉴를 나가면 적용됩니다.",
        "lan.name": "LAN 접근 허용",
        "lan.desc": "네트워크의 다른 기기(휴대폰, 태블릿, 다른 PC)에도 지도를 제공합니다. Windows가 방화벽에서 게임 허용을"
                    " 물을 수 있습니다. 끔: 이 PC에서만 열 수 있습니다.",
        "rate.name": "읽기 빈도",
        "rate.desc": "모드가 1초에 게임을 읽어 페이지로 보내는 횟수(그 사이의 움직임은 페이지가 부드럽게 합니다). 낮을수록"
                     " 게임과 지도 공유 시 업로드 부담이 줄어듭니다.",
        "auto.name": "자동 업데이트",
        "auto.desc": "하루에 한 번 GitHub에서 Helios Tracker의 새 버전을 찾아 설치하고 모드를 다시 불러옵니다."
                     " 끔: 업데이트 확인을 누를 때만.",
        "check.name": "업데이트 확인",
        "check.desc": "지금 Helios Tracker의 새 버전을 찾고, 설치하기 전에 묻습니다.",
        "box.title": "Helios Tracker",
        "box.updateTitle": "Helios Tracker 업데이트",
        "update.checking": "업데이트 확인 중...",
        "update.downloading": "Helios Tracker {tag} 다운로드 중...",
        "update.cancel": "취소",
        "update.available": "Helios Tracker {tag}을(를) 사용할 수 있습니다(현재 {ours}).",
        "update.download": "다운로드 및 설치",
        "update.notNow": "나중에 하기",
        "update.installFailed": "{tag}을(를) 설치할 수 없습니다:\n{error}",
        "update.ok": "확인",
        "update.installed": "Helios Tracker {tag}이(가) 설치되었습니다: 다음 게임 실행부터 사용됩니다(이번 세션은 {ours}).",
        "update.reloadNow": "지금 다시 불러오기",
        "update.later": "나중에",
        "update.latest": "최신 버전입니다({ours}).",
        "update.checkFailed": "업데이트를 확인할 수 없습니다:\n{error}",
        "update.updated": "Helios Tracker가 {tag}(으)로 업데이트되었습니다",
        "update.unknownVersion": "알 수 없는 버전",
    },
    "zh": {
        "mod.desc": "在網頁瀏覽器中顯示目前關卡的即時地圖：遊戲地圖上標示玩家、敵人、NPC、載具和戰利品，可縮放和拖曳。",
        "open.name": "在瀏覽器中開啟地圖",
        "open.desc": "在預設瀏覽器中開啟即時地圖（模組必須已啟用）。",
        "port.name": "連接埠",
        "port.desc": "本機網頁伺服器的連接埠：頁面位於 http://localhost:<port>/。離開此選單時套用。",
        "lan.name": "允許區域網路存取",
        "lan.desc": "也將地圖提供給網路中的其他裝置（手機、平板、另一台電腦）。Windows 可能會詢問是否讓遊戲通過防火牆。"
                    "關閉：只有這台電腦能開啟。",
        "rate.name": "讀取頻率",
        "rate.desc": "模組每秒讀取遊戲並傳送到頁面的次數（頁面會平滑其間的移動）。越低：遊戲負擔越輕，分享地圖時的上傳量也越少。",
        "auto.name": "自動更新",
        "auto.desc": "每天一次在 GitHub 上尋找 Helios Tracker 的新版本，安裝後重新載入模組。關閉：只在按下「檢查更新」時。",
        "check.name": "檢查更新",
        "check.desc": "立即尋找 Helios Tracker 的新版本，安裝前會先詢問。",
        "box.title": "Helios Tracker",
        "box.updateTitle": "Helios Tracker 更新",
        "update.checking": "正在檢查更新...",
        "update.downloading": "正在下載 Helios Tracker {tag}...",
        "update.cancel": "取消",
        "update.available": "Helios Tracker {tag} 已可使用（目前為 {ours}）。",
        "update.download": "下載並安裝",
        "update.notNow": "暫時不要",
        "update.installFailed": "無法安裝 {tag}：\n{error}",
        "update.ok": "確定",
        "update.installed": "Helios Tracker {tag} 已安裝：將從下次啟動遊戲時開始使用（本次執行的是 {ours}）。",
        "update.reloadNow": "立即重新載入",
        "update.later": "稍後",
        "update.latest": "已是最新版本（{ours}）。",
        "update.checkFailed": "無法檢查更新：\n{error}",
        "update.updated": "Helios Tracker 已更新至 {tag}",
        "update.unknownVersion": "未知版本",
    },
    "ru": {
        "mod.desc": "Живая карта текущего уровня в вашем браузере: карта игры с игроками, врагами, NPC, транспортом и"
                    " добычей, с масштабом и перемещением.",
        "open.name": "Открыть карту в браузере",
        "open.desc": "Открывает живую карту в браузере по умолчанию (мод должен быть включён).",
        "port.name": "Порт",
        "port.desc": "Порт локального веб-сервера: страница доступна по адресу http://localhost:<port>/. Применяется при"
                     " выходе из этого меню.",
        "lan.name": "Доступ по локальной сети",
        "lan.desc": "Также показывает карту другим устройствам в вашей сети (телефону, планшету, другому ПК). Windows"
                    " может попросить разрешить игру в брандмауэре. Выкл.: открыть её может только этот ПК.",
        "rate.name": "Частота опроса",
        "rate.desc": "Сколько раз в секунду мод читает игру и отправляет данные на страницу (страница сглаживает движение"
                     " между ними). Ниже: меньше нагрузки на игру и на исходящий канал, когда вы делитесь картой.",
        "auto.name": "Автоматические обновления",
        "auto.desc": "Раз в день ищет новую версию Helios Tracker на GitHub, устанавливает её и перезагружает мод."
                     " Выкл.: только когда вы нажимаете «Проверить обновления».",
        "check.name": "Проверить обновления",
        "check.desc": "Ищет новую версию Helios Tracker прямо сейчас и спрашивает перед установкой.",
        "box.title": "Helios Tracker",
        "box.updateTitle": "Обновление Helios Tracker",
        "update.checking": "Проверка обновлений...",
        "update.downloading": "Загрузка Helios Tracker {tag}...",
        "update.cancel": "Отмена",
        "update.available": "Доступна версия Helios Tracker {tag} (у вас {ours}).",
        "update.download": "Скачать и установить",
        "update.notNow": "Не сейчас",
        "update.installFailed": "Не удалось установить {tag}:\n{error}",
        "update.ok": "ОК",
        "update.installed": "Helios Tracker {tag} установлен: он будет работать со следующего запуска игры (сейчас"
                            " работает {ours}).",
        "update.reloadNow": "Перезагрузить сейчас",
        "update.later": "Позже",
        "update.latest": "У вас последняя версия ({ours}).",
        "update.checkFailed": "Не удалось проверить обновления:\n{error}",
        "update.updated": "Helios Tracker обновлён до {tag}",
        "update.unknownVersion": "неизвестная версия",
    },
}

_lang = ["en"]


def set_game_language(game_code: str) -> None:
    """The game's GetLanguage ("INT", "FRA"...): the catalog used from now on (unknown: English)."""
    _lang[0] = GAME_LANGS.get((game_code or "").upper(), "en")


def language() -> str:
    return _lang[0]


def t(key: str, **values: object) -> str:
    """The text in the game's language (English if a key were missing there), {name} filled from `values`."""
    text = TEXT.get(_lang[0], {}).get(key) or TEXT["en"][key]
    return text.format(**values) if values else text
