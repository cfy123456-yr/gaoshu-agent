import importlib.util
import io
import itertools
import json
import struct
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import ANY, MagicMock, patch

from deploy import (
    demo_chat,
    demo_coze_ocr,
    demo_math_text,
    demo_question_blocks,
    demo_remote_image,
    demo_session,
    demo_vision,
    demo_windows_ocr,
    wsgi_app,
)


class DemoPageTest(unittest.TestCase):
    def setUp(self):
        self.client = wsgi_app.application.test_client()
        wsgi_app._chat_response_cache.clear()
        wsgi_app._ocr_response_cache.clear()
        wsgi_app.teaching_sessions.clear()
        wsgi_app.rate_limiter.requests.clear()
        self.session_counter = itertools.count(1)

    def chat(
        self,
        message,
        history=None,
        session=None,
        mode=None,
        *,
        teaching_action=None,
        source=None,
        pending_question=None,
    ):
        session_id = session or next(self.session_counter)
        headers = {"X-Demo-Session": f"test-session-{session_id}"}
        payload = {"message": message, "history": history or []}
        if mode is not None:
            payload["mode"] = mode
        if teaching_action is not None:
            payload["teaching_action"] = teaching_action
        if source is not None:
            payload["source"] = source
        if pending_question is not None:
            payload["pending_question"] = pending_question
        return self.client.post(
            "/demo/api/chat",
            json=payload,
            headers=headers,
        )

    def test_demo_page_is_available(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("知微老师", html)
        self.assertIn("/demo/api/chat", html)
        self.assertIn('id="chatInput"', html)
        self.assertIn('id="messageList"', html)
        self.assertIn("/static/katex/katex.min.css", html)
        self.assertIn("/static/katex/katex.min.js", html)
        self.assertIn("/static/morphicons/element.js", html)
        self.assertIn("defineMorphIcon();", html)
        self.assertIn("<morph-icon", html)
        self.assertIn("function setMorphIcon(target, iconPath)", html)
        self.assertIn('target.setAttribute("icon", iconPath)', html)
        self.assertIn("function createMorphIcon(iconPath, options = {})", html)
        self.assertIn("createMorphIcon(MORPH_ICONS.close", html)
        self.assertIn('aria-label="选择题目图片"', html)
        self.assertIn('id="suggestions"\n          role="group"', html)
        self.assertIn('aria-valuemin="220"', html)
        self.assertIn('aria-valuemax="420"', html)
        self.assertIn(
            'sidebarResizer.setAttribute("aria-valuenow", String(nextWidth));',
            html,
        )
        self.assertIn('id="messageList"\n          aria-label=', html)
        self.assertIn('tabindex="0"\n        ></main>', html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertNotIn("serviceStatus", html)
        self.assertNotIn("serviceStatusText", html)
        self.assertNotIn("status-chip", html)
        self.assertNotIn("服务在线", html)
        self.assertNotIn("服务离线", html)
        self.assertNotIn("checkService", html)
        self.assertNotIn('fetch("/demo/api/health"', html)
        self.assertIn('fetch("/demo/api/chat"', html)

    def test_demo_page_exposes_accessible_math_input_toolbar(self):
        html = self.client.get("/demo").get_data(as_text=True)

        self.assertIn('id="mathToolbar"', html)
        self.assertIn('aria-label="插入数学符号"', html)
        self.assertIn('id="mathLimitsToggle"', html)
        self.assertIn('id="mathLimitsPanel"', html)
        self.assertIn('id="mathLowerLimit"', html)
        self.assertIn('id="mathUpperLimit"', html)
        self.assertIn('id="mathCustomLimitToggle"', html)
        self.assertIn('id="mathCustomLimitPanel"', html)
        self.assertIn('id="mathLimitVariable"', html)
        self.assertIn('id="mathLimitPoint"', html)
        self.assertIn('id="mathLimitDirection"', html)
        self.assertIn('id="mathInsertLimit"', html)
        self.assertIn('class="math-tool-group"', html)
        self.assertIn('data-math-insert="lim_{x→0} "', html)
        self.assertIn('data-math-wrap-end="^{2}"', html)
        self.assertIn('data-math-wrap-end="^{n}"', html)
        self.assertIn('data-math-wrap-start="√("', html)
        self.assertIn('data-math-wrap-start="∛("', html)
        self.assertIn('data-math-insert="()/()"', html)
        self.assertIn('data-math-insert="d/dx "', html)
        self.assertIn('data-math-insert="e^{x}"', html)
        self.assertIn('data-math-insert="∞"', html)
        self.assertIn('data-math-insert="≠"', html)
        self.assertIn("function insertMathInputText(text, options = {})", html)
        self.assertIn('chatInput.setRangeText(insertion, start, end, "end")', html)
        self.assertIn("function insertDefiniteIntegral()", html)
        self.assertIn("function setMathCustomLimitOpen(open)", html)
        self.assertIn("function insertCustomLimit()", html)
        self.assertIn(
            "`∫_{${lower}}^{${upper}} ${integrand} dx`",
            html,
        )
        self.assertIn(
            "`lim_{${variable}→${point}${directionSuffix}} ${expression}`",
            html,
        )

    def test_demo_page_exposes_clickable_standard_input_examples(self):
        html = self.client.get("/demo").get_data(as_text=True)

        self.assertIn('id="inputGuide"', html)
        self.assertIn('id="inputGuideText"', html)
        self.assertIn('aria-label="规范输入示例"', html)
        self.assertIn(
            'aria-describedby="inputGuideText voiceStatus"',
            html,
        )
        self.assertIn(
            "自然语言也能识别；点击示例填入后",
            html,
        )
        self.assertIn(
            'data-input-example="当 x 从 0 到 pi 时 sin(x) 的定积分"',
            html,
        )
        self.assertIn(
            'data-input-example="极限 x→0 sin(x)/x"',
            html,
        )
        self.assertIn(
            'data-input-example="求 z=x^2*y 在点 (1,2) 处对 x 的偏导数"',
            html,
        )
        self.assertIn(
            'data-input-example="y的导数减y等于0"',
            html,
        )
        self.assertIn(
            'data-input-example="一般项 1/n^2 是否收敛"',
            html,
        )
        self.assertIn("function fillInputExample(button)", html)
        self.assertIn("chatInput.value = example;", html)
        self.assertIn(
            "chatInput.setSelectionRange(example.length, example.length);",
            html,
        )
        self.assertIn(
            'event.target.closest("[data-input-example]")',
            html,
        )
        self.assertIn(
            "inputGuide.open ? MORPH_ICONS.chevronUp : MORPH_ICONS.chevronDown",
            html,
        )
        self.assertIn(".input-guide-icon svg,", html)
        self.assertIn(".input-guide-chevron svg {", html)
        self.assertIn("width: 14px;", html)
        self.assertIn("flex: 0 0 14px;", html)

    def test_demo_page_loads_with_pythonanywhere_dynamic_loader(self):
        module_path = Path(__file__).resolve().parents[1] / "deploy" / "wsgi_app.py"
        spec = importlib.util.spec_from_file_location(
            "dynamic_pythonanywhere_wsgi_test",
            module_path,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        client = module.application.test_client()
        response = client.get("/demo")
        self.assertEqual(200, response.status_code)
        self.assertIn("/static/katex/katex.min.css", response.get_data(as_text=True))
        static_response = client.get("/static/morphicons/element.js")
        try:
            self.assertEqual(200, static_response.status_code)
        finally:
            static_response.close()

    def test_demo_page_morphicon_assets_are_served(self):
        for filename in (
            "element.js",
            "controller-CXZuwJ_M.js",
            "spring-CFHloqPP.js",
            "normalize-CYnN3Npw.js",
            "dom.js",
        ):
            with self.subTest(filename=filename):
                response = self.client.get(f"/static/morphicons/{filename}")
                try:
                    self.assertEqual(200, response.status_code)
                finally:
                    response.close()

    def test_chat_logs_do_not_include_raw_message(self):
        private_message = "PRIVATE-QUESTION-7f31"

        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", ""),
            self.assertLogs(wsgi_app.application.logger, level="WARNING") as logs,
        ):
            response = self.chat(private_message, session="privacy")

        self.assertEqual(200, response.status_code)
        log_output = "\n".join(logs.output)
        self.assertNotIn(private_message, log_output)
        self.assertIn("message_length=", log_output)

    def test_demo_page_supports_browser_voice_input_and_answer_speech(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn('id="voiceInputButton"', html)
        self.assertIn('id="voiceStatus"', html)
        self.assertIn(
            'aria-describedby="inputGuideText voiceStatus"',
            html,
        )
        self.assertIn(
            "window.SpeechRecognition || window.webkitSpeechRecognition || null",
            html,
        )
        self.assertIn("window.speechSynthesis", html)
        self.assertIn("window.SpeechSynthesisUtterance", html)
        self.assertIn('recognition.lang = "zh-CN"', html)
        self.assertIn("recognition.interimResults = true", html)
        self.assertIn("function normalizeSpokenMathText(", html)
        self.assertIn("function speechFriendlyMathText(", html)
        self.assertIn("function applyVoiceDraft(", html)
        self.assertIn("function startVoiceInput(", html)
        self.assertIn("function stopVoiceInput(", html)
        self.assertIn("function stopVoiceInteraction(", html)
        self.assertIn("function toggleAnswerSpeech(", html)
        self.assertIn('data-message-action="speak-answer"', html)
        self.assertIn(
            "voiceInputButton.hidden = !BrowserSpeechRecognition",
            html,
        )
        self.assertIn(
            "composerRow.dataset.voiceAvailable = voiceAvailable",
            html,
        )
        self.assertIn('window.addEventListener("pagehide", stopVoiceInteraction)', html)

    def test_demo_page_exposes_chapter_solver(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn('id="solverDialog"', html)
        self.assertNotIn('id="openSolverButton"', html)
        self.assertIn("const SOLVER_CHAPTERS = {", html)
        self.assertIn('fetch("/demo/api/solve"', html)
        self.assertIn('data.intent === "solve"', html)
        self.assertIn("populateSolverChapters();", html)
        self.assertIn('solverDialog.showModal()', html)
        self.assertIn("parametric_derivative", html)
        self.assertIn("参数方程求导", html)
        self.assertIn("system_implicit_derivative", html)
        self.assertIn("方程组确定函数求偏导", html)
        self.assertIn("conditional_extrema", html)
        self.assertIn("条件极值", html)
        self.assertIn("double_polar", html)
        self.assertIn("极坐标二重积分", html)
        self.assertIn("triple_cylindrical", html)
        self.assertIn("柱面坐标三重积分", html)
        self.assertIn("triple_spherical", html)
        self.assertIn("球面坐标三重积分", html)
        self.assertIn("line_scalar_explicit", html)
        self.assertIn("第一类曲线积分（显式曲线）", html)
        self.assertIn("line_vector_explicit", html)
        self.assertIn("第二类曲线积分（显式曲线）", html)
        self.assertIn("surface_scalar_explicit", html)
        self.assertIn("第一类曲面积分（显式曲面）", html)
        self.assertIn("flux_explicit", html)
        self.assertIn("第二类曲面积分（显式曲面）", html)

    def test_demo_page_auto_generates_question_knowledge(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertNotIn('id="formulaDialog"', html)
        self.assertNotIn("const FORMULA_GUIDES = {", html)
        self.assertNotIn("function openFormulaDialog(type)", html)
        self.assertIn('id="questionKnowledge"', html)
        self.assertIn('id="questionKnowledgeList"', html)
        self.assertIn('id="questionKnowledgeStatus"', html)
        self.assertIn("const QUESTION_KNOWLEDGE_RULES = [", html)
        self.assertIn("function renderQuestionKnowledge(", html)
        self.assertIn("function queueQuestionKnowledgeUpdate(", html)
        self.assertIn("queueQuestionKnowledgeUpdate(chatInput.value)", html)
        self.assertIn("function renderQuestionKnowledgePending()", html)
        self.assertIn("function renderQuestionKnowledgeBlocked(", html)
        self.assertIn("function syncQuestionKnowledgeFromMessage(", html)
        self.assertIn("function syncQuestionKnowledgeFromConversation(", html)
        self.assertIn("function isVerifiedTeachingMessage(", html)
        self.assertIn('source: "solution"', html)
        self.assertIn("renderQuestionKnowledge(\"\")", html)
        self.assertIn('aria-live="polite"', html)
        self.assertNotIn("FORMULA_COLLECTION", html)
        self.assertNotIn("formulaCardGrid", html)
        self.assertNotIn("formulaSearchInput", html)
        self.assertNotIn("renderFormulaCards", html)

    def test_verified_solution_knowledge_has_one_server_owned_source(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn(
            "function solutionKnowledgeFor(message) {",
            html,
        )
        self.assertIn(
            "return normalizeKnowledgePoints(message && message.knowledgePoints)\n"
            "          .slice(0, 4);",
            html,
        )
        self.assertNotIn(
            "localMatchedQuestionKnowledge(sourceUserMessage.text)",
            html,
        )
        self.assertNotIn(
            "先明确已知条件、目标量和所求形式；计算后再用代入、量纲或边界情况检查结果。",
            html,
        )
        self.assertIn("if (viewModel.knowledge.length) {", html)
        self.assertIn(
            "return remoteMatches.length ? remoteMatches : localMatches;",
            html,
        )

    def test_unverified_solution_never_renders_raw_reply(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn(
            "function solutionFailureTextForMessage(message) {",
            html,
        )
        self.assertIn(
            "自动求解未通过统一验算，已停止后续流程。",
            html,
        )
        self.assertIn(
            "const displayText = unverifiedSolutionIntent",
            html,
        )
        self.assertIn(
            "? solutionFailureTextForMessage(message)",
            html,
        )
        self.assertIn(
            "renderRichMessageText(text, displayText);",
            html,
        )
        self.assertIn(
            "return speechFriendlyMathText(\n"
            "            solutionFailureTextForMessage(message),\n"
            "          );",
            html,
        )

    def test_demo_page_keeps_only_two_sidebar_entries(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertEqual(2, html.count('data-toolbox-tab="'))
        self.assertEqual(2, html.count('data-toolbox-panel="'))
        for tab in ("wrongbook", "progress"):
            self.assertIn(f'data-toolbox-tab="{tab}"', html)
            self.assertIn(f'data-rail-tab="{tab}"', html)
        self.assertNotIn('data-toolbox-tab="formulas"', html)
        self.assertNotIn('data-toolbox-panel="formulas"', html)
        self.assertNotIn('data-rail-tab="formulas"', html)
        self.assertNotIn('data-toolbox-tab="calculator"', html)
        self.assertNotIn('data-toolbox-panel="calculator"', html)
        self.assertNotIn('id="relatedKnowledge"', html)
        self.assertNotIn("function insertIntoChatInput(", html)
        self.assertNotIn('id="toolsNavList"', html)
        self.assertNotIn('id="toolsMenuCount"', html)
        self.assertNotIn('class="tools-menu"', html)

    def test_demo_page_exposes_toolbox_without_legacy_preview_panel(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        for field in ("conversationPanel",):
            self.assertIn(f'id="{field}"', html)
        for removed_id in (
            "previewPanel",
            "previewContent",
            "previewToggle",
            "previewClear",
        ):
            self.assertNotIn(f'id="{removed_id}"', html)
        for removed_id in (
            "quickLimitForm",
            "quickDerivativeForm",
            "quickIndefiniteForm",
            "quickDefiniteForm",
            "quickDifferentialForm",
            "quickPlotForm",
            "formulaSearchInput",
            "formulaCardGrid",
        ):
            self.assertNotIn(f'id="{removed_id}"', html)
        for image_field in (
            "imageUploadButton",
            "imageFileInput",
            "composerImagePreview",
            "composerImageList",
            "composerImageStatus",
            "composerImageClear",
        ):
            self.assertIn(f'id="{image_field}"', html)
        self.assertNotIn('id="composerImageRemove"', html)
        self.assertIn("async function sendMessage(rawMessage, options = {})", html)
        self.assertIn("addQuestionImages(imageFileInput.files)", html)
        self.assertIn("clearQuestionImages({ revokeUrls: false })", html)
        self.assertIn('fetch("/demo/api/ocr"', html)
        self.assertIn("function renderQuestionKnowledge(", html)
        self.assertNotIn("function insertIntoChatInput(", html)
        self.assertIn("composer-image-question-picker", html)
        self.assertIn("function toggleRecognizedQuestion(", html)
        self.assertIn('"全选",', html)
        self.assertIn('setAttribute("aria-label", "全选所有识别题目")', html)
        self.assertIn("按当前识别题继续", html)
        self.assertIn("function setConversationPanelCollapsed(", html)
        self.assertNotIn("function setPreviewCollapsed(", html)
        self.assertNotIn("\u8ba1\u7b97\u8fc7\u7a0b\u603b\u89c8", html)
        self.assertNotIn(
            "\u89e3\u9898\u8fc7\u7a0b\u4e0e\u7ed3\u679c\u4f1a\u663e\u793a\u5728\u8fd9\u91cc",
            html,
        )
        self.assertNotIn("结果预览", html)
        self.assertIn('toolbox.addEventListener("click"', html)
        self.assertNotIn('data-focus-target="quickLimitExpression"', html)
        self.assertNotIn("const collapsedQuickTool = event.target.closest(", html)
        self.assertNotIn("图片识别（暂未接入）", html)
        self.assertNotIn("该工具尚未接线", html)

    def test_demo_page_supports_image_only_and_multiple_image_messages(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertRegex(
            html,
            r'id="imageFileInput"\s+type="file"\s+accept="[^"]+"\s+'
            r'aria-label="[^"]+"\s+multiple',
        )
        self.assertIn("const MAX_QUESTION_IMAGE_COUNT = 4", html)
        self.assertIn(
            "const MAX_QUESTION_IMAGE_INPUT_BYTES = 20 * 1024 * 1024",
            html,
        )
        self.assertIn("const MAX_QUESTION_IMAGE_EDGE = 1600", html)
        self.assertIn("let questionImageRecognitionQueue = Promise.resolve()", html)
        self.assertIn("async function prepareQuestionImage(file)", html)
        self.assertIn("function enqueueQuestionImageRecognition(item)", html)
        self.assertIn("canvas.toBlob(", html)
        self.assertIn("function addQuestionImages(fileList)", html)
        self.assertIn("async function submitComposer()", html)
        self.assertIn("function syncComposerState()", html)
        self.assertIn("function flushPendingComposerSubmission()", html)
        self.assertIn("function selectedBlockIndexes(item)", html)
        self.assertIn("function setAllRecognizedQuestions(item, picker, selected)", html)
        self.assertIn("function composeQuestionRequests()", html)
        self.assertIn('confirmedOcr ? "\\u786e\\u8ba4" : text', html)
        self.assertIn("await sendMessage(", html)
        self.assertIn(
            "attachments: index === 0 ? attachments : []",
            html,
        )
        self.assertIn(
            "!pendingQuestionImages.length && !hasNotice",
            html,
        )
        self.assertIn(
            "composerImageStatus.textContent = composerImageNotice;",
            html,
        )
        self.assertIn("pendingComposerSubmission = true", html)
        self.assertIn("hasPendingImage", html)
        self.assertIn("hasRecognizedImage", html)
        self.assertIn("submitComposer();", html)
        self.assertIn("const WELCOME_TEXTS = [", html)
        self.assertIn(
            'const WELCOME_INDEX_KEY = "zhiwei-demo-welcome-index-v1"',
            html,
        )
        self.assertIn("function welcomeMessage()", html)
        self.assertIn("sessionStorage.getItem(WELCOME_INDEX_KEY)", html)
        self.assertIn("sessionStorage.setItem(", html)
        self.assertIn(
            ".filter((index) => index !== previousIndex)",
            html,
        )

    def test_demo_page_uses_warm_copy_and_structured_solution_cards(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("写下你的题目", html)
        self.assertIn(
            "嗨，我是知微 👋 今天哪道高数题卡住了？"
            "文字、拍照都行，我们一步步来。",
            html,
        )
        self.assertIn('.message[data-intent="welcome"] .bubble', html)
        self.assertIn('messageList.dataset.welcomeOnly', html)
        self.assertIn("renderWelcomeMessageText(text, message)", html)
        self.assertIn('"welcome-message-lead"', html)
        self.assertIn('"welcome-message-body"', html)
        self.assertIn(
            "const legacyWelcome =\n              intent === \"welcome\" && "
            "!WELCOME_TEXTS.includes(text)",
            html,
        )
        self.assertIn("text: normalizedWelcomeText", html)
        self.assertIn("welcomeLead: legacyWelcome", html)
        self.assertIn("String(item.welcomeLead || welcomeParts.lead)", html)
        self.assertIn("welcomeBody: legacyWelcome", html)
        self.assertIn("String(item.welcomeBody || welcomeParts.body)", html)
        self.assertIn('article.dataset.intent = message.intent || ""', html)
        self.assertIn("function suggestionIcon(name)", html)
        for icon in ("camera", "check", "book"):
            self.assertIn(f'icon: "{icon}"', html)
        self.assertIn('element("span", "suggestion-label", suggestion.label)', html)
        self.assertRegex(
            html,
            r"\.suggestion-label\s*\{[^}]*min-width:\s*max-content;",
        )
        self.assertRegex(
            html,
            r"\.suggestions-toggle\s*\{[^}]*white-space:\s*nowrap;",
        )
        self.assertIn("function renderSolutionSteps(container, message)", html)
        self.assertIn('"solution-step-list"', html)
        self.assertIn("`第${index + 1}步`", html)
        self.assertIn("这步没看懂", html)
        self.assertIn("我懂了，加入错题本", html)
        self.assertIn('element("span", "speech-button-label", "朗读答案")', html)
        self.assertIn('button.querySelector(".speech-button-label")', html)
        self.assertIn(
            'explainButton.dataset.messageAction = "explain-step"',
            html,
        )
        self.assertIn("renderedSolutionSheet = true", html)
        self.assertIn("!renderedSolutionSheet", html)

    def test_demo_page_keeps_the_sidebar_rail_minimal(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertRegex(
            html,
            r'data-toolbox-panel="wrongbook"\s+'
            r'data-active="true"\s+'
        )
        self.assertNotIn('id="moreToolsToggle"', html)
        self.assertNotIn('id="relatedKnowledgeList"', html)
        self.assertNotIn('data-rail-tool="true"', html)
        self.assertNotIn("data-more-expanded", html)
        self.assertEqual(3, html.count('class="sidebar-rail-button"'))
        self.assertRegex(
            html,
            r'<div class="conversation-panel-actions">\s*'
            r'<button\s+class="icon-button new-chat-icon"\s+'
            r'id="newChatButton"',
        )
        self.assertIn('.sidebar-rail-button', html)
        self.assertIn(
            '.app-shell[data-sidebar-collapsed="true"] .sidebar-rail',
            html,
        )
        self.assertNotIn(".quick-tool > *", html)

    def test_demo_page_exposes_question_knowledge_and_wrong_book_tools(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn('data-toolbox-tab="wrongbook"', html)
        self.assertIn('id="questionKnowledgeList"', html)
        self.assertIn('id="wrongBookList"', html)
        self.assertIn("const QUESTION_KNOWLEDGE_RULES = [", html)
        self.assertIn('const WRONG_BOOK_KEY = "zhiwei-demo-wrong-book-v1"', html)
        self.assertIn("function renderQuestionKnowledge(", html)
        self.assertIn("function toggleWrongBook(messageId)", html)
        self.assertIn("function practiceWrongBookItem(itemId)", html)
        self.assertIn("function syncWrongBookAnswer(messageId, questionText", html)
        self.assertIn('"toggle-wrongbook"', html)
        self.assertIn('id="wrongBookExport"', html)
        self.assertIn("function exportWrongBook()", html)
        self.assertIn("wrongBookExport.addEventListener", html)
        self.assertIn("重新练习", html)
        self.assertIn("查看参考答案", html)

    def test_demo_page_only_offers_wrong_book_for_resolved_math_answers(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("const WRONG_BOOK_ELIGIBLE_INTENTS = new Set([", html)
        for intent in ("verify", "integrate", "limit", "solve", "plot"):
            self.assertIn(f'"{intent}"', html)
        self.assertIn("function messageCanJoinWrongBook(message)", html)
        self.assertIn("function isVerifiedSolutionMessage(message)", html)
        self.assertIn("message.verified !== true", html)
        self.assertIn("verification.passed !== true", html)
        self.assertIn("!Array.isArray(checks)", html)
        self.assertIn("!checks.length", html)
        self.assertIn("Object.keys(calculation).length", html)
        self.assertIn(
            "if (!answer || !isVerifiedSolutionMessage(answer)) {",
            html,
        )
        self.assertIn(
            "if (!isVerifiedSolutionMessage(message)) {",
            html,
        )
        self.assertIn("function solutionKnowledgeFor(message)", html)
        self.assertIn(
            "return normalizeKnowledgePoints(message && message.knowledgePoints)",
            html,
        )
        self.assertIn(".slice(0, 4);", html)
        self.assertIn(
            '!WRONG_BOOK_ELIGIBLE_INTENTS.has(String(answer.intent || ""))',
            html,
        )
        self.assertIn("const intent = String(item.intent || \"\")", html)
        self.assertIn("intent: String(data.intent || \"\")", html)
        self.assertIn('message.role === "assistant"', html)
        self.assertIn("&& !renderedSolutionSheet", html)
        self.assertIn(
            "sourceUserMessage",
            html,
        )
        self.assertIn(
            "bookmarkButton.dataset.messageId = sourceUserMessage.id",
            html,
        )
        self.assertIn(
            'bookmarkButton.dataset.messageAction = "toggle-wrongbook"',
            html,
        )
        self.assertIn(
            'bookmarked ? "已加入错题集" : "加入错题集"',
            html,
        )
        self.assertIn(
            "确认这是一道需要收录的错题吗？加入后可在错题集里重练。",
            html,
        )
        self.assertIn(
            'window.confirm("确认从错题集移除这道题吗？")',
            html,
        )
        self.assertIn(
            "setSuggestionsCollapsed(false)",
            html,
        )
        self.assertIn(
            'const conversationPanelMedia = window.matchMedia("(max-width: 1120px)")',
            html,
        )
        self.assertIn("grid-template-areas:", html)

    def test_demo_page_exposes_learning_progress_import_export(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        for field in (
            "learningProgressQuestions",
            "learningProgressCalculations",
            "learningProgressPractice",
            "learningProgressWrongBook",
            "learningProgressStreak",
            "learningProgressDays",
            "learningProgressDaysList",
            "learningProgressExport",
            "learningProgressBackup",
            "learningProgressMerge",
            "learningProgressOverwrite",
            "learningProgressImportInput",
            "learningProgressStatus",
        ):
            self.assertIn(f'id="{field}"', html)
        self.assertIn('data-toolbox-tab="progress"', html)
        self.assertIn('data-toolbox-panel="progress"', html)
        self.assertIn('"zhiwei-demo-learning-progress-v1"', html)
        self.assertIn("function renderLearningProgress()", html)
        self.assertIn("function exportLearningProgress()", html)
        self.assertIn("function exportLearningProgressBackup()", html)
        self.assertIn("function importLearningProgress(file", html)
        self.assertIn("知微高数_学习报告_", html)
        self.assertIn("知微高数_学习进度备份_", html)
        self.assertIn("function clampProgressTimestamp(value)", html)
        self.assertIn(
            "progress.updatedAt = clampProgressTimestamp(source.updatedAt)",
            html,
        )
        self.assertIn('recordLearningActivity("question")', html)
        self.assertIn('recordLearningActivity("calculation")', html)
        self.assertIn('recordLearningActivity("practice")', html)
        self.assertIn(
            'learningProgressImportInput.addEventListener("change"',
            html,
        )

    def test_demo_health_is_available(self):
        with patch.object(wsgi_app, "vision_ocr_configured", return_value=False):
            response = self.client.get("/demo/api/health")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertTrue(payload["demo"]["available"])
        self.assertEqual("/demo", payload["demo"]["page"])
        self.assertEqual("coze", payload["ocr"]["provider"])
        self.assertIsInstance(payload["ocr"]["configured"], bool)
        self.assertIn(
            payload["ocr"]["coze_mode"],
            {"workflow", "bot", "unconfigured"},
        )

    def test_demo_health_reports_model_configuration_without_leaking_keys(self):
        with (
            patch.object(demo_chat, "_GENERAL_CHAT_API_KEY", "general-secret"),
            patch.object(demo_chat, "_VISION_API_KEY", ""),
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "general-secret"),
            patch.object(
                demo_chat,
                "GENERAL_CHAT_API_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            ),
            patch.object(demo_chat, "GENERAL_CHAT_MODEL", "qwen-plus"),
            patch.object(wsgi_app, "vision_ocr_configured", return_value=True),
            patch.object(wsgi_app, "vision_provider", return_value="dashscope"),
            patch.object(wsgi_app, "VISION_MODEL", "qwen3-vl-plus"),
        ):
            response = self.client.get("/demo/api/health")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("dashscope", payload["ocr"]["vision_provider"])
        self.assertEqual("qwen3-vl-plus", payload["ocr"]["vision_model"])
        general_chat = payload["general_chat"]
        self.assertTrue(general_chat["configured"])
        self.assertEqual("dashscope", general_chat["provider"])
        self.assertEqual("qwen-plus", general_chat["model"])
        self.assertEqual("dedicated", general_chat["key_source"])
        self.assertEqual(30.0, general_chat["timeout_seconds"])
        self.assertNotIn("general-secret", response.get_data(as_text=True))

    def test_demo_health_reports_vision_key_fallback_for_general_chat(self):
        with (
            patch.object(demo_chat, "_GENERAL_CHAT_API_KEY", ""),
            patch.object(demo_chat, "_VISION_API_KEY", "vision-secret"),
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "vision-secret"),
            patch.object(
                demo_chat,
                "GENERAL_CHAT_API_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            ),
            patch.object(demo_chat, "GENERAL_CHAT_MODEL", "qwen-plus"),
        ):
            response = self.client.get("/demo/api/health")

        self.assertEqual(200, response.status_code)
        general_chat = response.get_json()["general_chat"]
        self.assertTrue(general_chat["configured"])
        self.assertEqual("vision_fallback", general_chat["key_source"])
        self.assertNotIn("vision-secret", response.get_data(as_text=True))

    def test_demo_health_reports_ocr_configuration_without_leaking_token(self):
        with (
            patch.object(demo_coze_ocr, "COZE_API_TOKEN", "secret-token"),
            patch.object(demo_coze_ocr, "COZE_BOT_ID", "test-bot"),
            patch.object(demo_coze_ocr, "COZE_OCR_WORKFLOW_ID", ""),
            patch.object(wsgi_app, "vision_ocr_configured", return_value=False),
            patch.object(demo_windows_ocr, "WINDOWS_OCR_FALLBACK", False),
        ):
            response = self.client.get("/demo/api/health")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertTrue(payload["ocr"]["configured"])
        self.assertEqual("bot", payload["ocr"]["coze_mode"])
        self.assertNotIn("secret-token", response.get_data(as_text=True))

    def test_demo_health_prefers_direct_vision_when_configured(self):
        with (
            patch.object(wsgi_app, "vision_ocr_configured", return_value=True),
            patch.object(demo_coze_ocr, "COZE_API_TOKEN", ""),
            patch.object(demo_coze_ocr, "COZE_BOT_ID", ""),
            patch.object(demo_coze_ocr, "COZE_OCR_WORKFLOW_ID", ""),
            patch.object(demo_windows_ocr, "WINDOWS_OCR_FALLBACK", False),
        ):
            response = self.client.get("/demo/api/health")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()["ocr"]
        self.assertEqual("vision", payload["provider"])
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["vision_configured"])
        self.assertFalse(payload["coze_configured"])
        self.assertEqual("unconfigured", payload["coze_mode"])

    def test_health_and_static_requests_do_not_consume_rate_limit(self):
        with patch.object(wsgi_app.rate_limiter, "check") as check:
            self.client.get("/demo/api/health")
            self.client.get("/health")
            self.client.get("/static/katex/katex.min.css").close()

        check.assert_not_called()

    def test_chat_requests_still_consume_rate_limit(self):
        with patch.object(wsgi_app.rate_limiter, "check") as check:
            self.client.post(
                "/demo/api/chat",
                json={"message": "x"},
            )

        check.assert_called_once()

    def test_demo_ocr_requires_an_image(self):
        response = self.client.post("/demo/api/ocr")

        self.assertEqual(400, response.status_code)
        self.assertIn("选择", response.get_json()["detail"])

    def test_demo_ocr_url_requires_an_image_url(self):
        response = self.client.post("/demo/api/ocr-url", json={})

        self.assertEqual(400, response.status_code)
        self.assertIn("image_url", response.get_json()["detail"])

    def test_demo_ocr_url_rejects_private_and_local_targets(self):
        for image_url in (
            "file:///etc/passwd",
            "http://localhost/a.png",
            "http://127.0.0.1/a.png",
            "http://10.0.0.8/a.png",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]/a.png",
            "https://example.com:8443/a.png",
        ):
            with self.subTest(image_url=image_url):
                response = self.client.post(
                    "/demo/api/ocr-url",
                    json={"image_url": image_url},
                )
                self.assertEqual(400, response.status_code)
                self.assertNotIn("latest/meta-data", response.get_json()["detail"])

    def test_remote_image_fetch_rejects_non_image_content(self):
        class FakeResponse:
            headers = {"Content-Type": "text/html"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, _limit):
                return b"<html>not an image</html>"

        with (
            patch.object(
                demo_remote_image,
                "validate_remote_image_url",
                return_value="https://images.example/a.png",
            ),
            patch.object(
                demo_remote_image,
                "build_opener",
                return_value=MagicMock(
                    open=MagicMock(return_value=FakeResponse())
                ),
            ),
        ):
            with self.assertRaises(demo_remote_image.RemoteImageError) as raised:
                demo_remote_image.fetch_remote_image(
                    "https://images.example/a.png"
                )

        self.assertIn("不是图片", str(raised.exception))

    def test_demo_ocr_url_downloads_image_before_running_vision_ocr(self):
        with (
            patch.object(
                wsgi_app,
                "validate_remote_image_url",
                return_value="https://images.example/question.png",
            ) as validate,
            patch.object(
                wsgi_app,
                "fetch_remote_image",
                return_value=(b"png-bytes", "image/png"),
            ) as fetch,
            patch.object(wsgi_app, "vision_ocr_configured", return_value=True),
            patch.object(
                wsgi_app,
                "transcribe_vision_question_image",
                return_value="计算不定积分 ∫ x e^(x^2) dx",
            ) as transcribe,
        ):
            response = self.client.get(
                "/demo/api/ocr-url",
                query_string={
                    "image_url": "https://images.example/question.png"
                },
                headers={"X-Demo-Session": "test-ocr-url-query"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("vision", payload["provider"])
        self.assertIn("∫ x e^(x^2) dx", payload["text"])
        self.assertTrue(payload["requires_confirmation"])
        validate.assert_called_once_with("https://images.example/question.png")
        fetch.assert_called_once_with("https://images.example/question.png")
        transcribe.assert_called_once_with(
            b"png-bytes",
            "image/png",
        )

    def test_demo_ocr_url_reuses_binary_ocr_cache(self):
        with (
            patch.object(
                wsgi_app,
                "validate_remote_image_url",
                return_value="https://images.example/question.png",
            ),
            patch.object(
                wsgi_app,
                "fetch_remote_image",
                return_value=(b"png-bytes", "image/png"),
            ) as fetch,
            patch.object(wsgi_app, "vision_ocr_configured", return_value=True),
            patch.object(
                wsgi_app,
                "transcribe_vision_question_image",
                return_value="计算积分 ∫ x e^(x^2) dx",
            ) as binary,
        ):
            first = self.client.post(
                "/demo/api/ocr-url",
                json={
                    "image_url": "https://images.example/question.png"
                },
            )
            second = self.client.post(
                "/demo/api/ocr-url",
                json={
                    "image_url": "https://images.example/question.png"
                },
            )

        self.assertEqual(200, first.status_code)
        self.assertEqual(200, second.status_code)
        self.assertFalse(first.get_json()["cache_hit"])
        self.assertTrue(second.get_json()["cache_hit"])
        self.assertEqual(2, fetch.call_count)
        binary.assert_called_once_with(b"png-bytes", "image/png")

    def test_demo_ocr_url_maps_download_failure_before_ocr(self):
        with (
            patch.object(
                wsgi_app,
                "validate_remote_image_url",
                return_value="https://images.example/question.png",
            ),
            patch.object(
                wsgi_app,
                "fetch_remote_image",
                side_effect=demo_remote_image.RemoteImageError(
                    "暂时无法下载图片，请稍后重试。",
                    status_code=502,
                ),
            ),
            patch.object(
                wsgi_app,
                "transcribe_vision_question_image",
            ) as transcribe,
        ):
            response = self.client.post(
                "/demo/api/ocr-url",
                json={
                    "image_url": "https://images.example/question.png"
                },
            )

        self.assertEqual(502, response.status_code)
        self.assertIn("暂时无法下载图片", response.get_json()["detail"])
        transcribe.assert_not_called()

    def test_demo_ocr_url_rejects_non_image_before_ocr(self):
        with (
            patch.object(
                wsgi_app,
                "validate_remote_image_url",
                return_value="https://example.com/",
            ),
            patch.object(
                wsgi_app,
                "fetch_remote_image",
                side_effect=demo_remote_image.RemoteImageError(
                    "图片链接返回的内容不是图片。"
                ),
            ),
            patch.object(
                wsgi_app,
                "transcribe_vision_question_image",
            ) as transcribe,
        ):
            response = self.client.post(
                "/demo/api/ocr-url",
                json={"image_url": "https://example.com/"},
            )

        self.assertEqual(400, response.status_code)
        self.assertIn("不是图片", response.get_json()["detail"])
        transcribe.assert_not_called()

    def test_ocr_question_validator_accepts_short_arithmetic(self):
        for question in ("1+1", "2+2", "8/2"):
            with self.subTest(question=question):
                self.assertTrue(demo_session.is_valid_ocr_question(question))

    def test_ocr_question_replaces_pending_question(self):
        store = demo_session.DemoSessionStore(ttl_seconds=60, max_sessions=10)

        store.remember_ocr_question("replace-question", "旧题 x^2")
        store.remember_ocr_question("replace-question", "1+1")

        pending = store.get("replace-question")
        self.assertEqual(demo_session.AWAITING_OCR_CONFIRMATION, pending.state)
        self.assertEqual("1+1", pending.pending_question)

    def test_demo_chat_uses_current_ocr_message_before_old_session(self):
        headers = {"X-Demo-Session": "test-ocr-message-order"}
        first = self.client.post(
            "/demo/api/chat",
            json={"message": "旧题 x^2", "source": "ocr"},
            headers=headers,
        )
        second = self.client.post(
            "/demo/api/chat",
            json={"message": "1+1", "source": "ocr"},
            headers=headers,
        )

        self.assertEqual(200, first.status_code)
        self.assertEqual(200, second.status_code)
        self.assertEqual("1+1", second.get_json()["formula_text"])

    def test_confirmation_uses_carried_question_when_session_is_missing(self):
        response = self.client.post(
            "/demo/api/chat",
            json={
                "message": "确认",
                "source": "text",
                "pending_question": "1+1",
            },
            headers={"X-Demo-Session": "test-missing-session-confirmation"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solving", payload["session_state"])
        self.assertEqual("1+1", payload["history_used"])

    def test_confirmation_prefers_carried_question_over_stale_session(self):
        headers = {"X-Demo-Session": "test-carried-question-priority"}
        self.client.post(
            "/demo/api/chat",
            json={"message": "旧题 x^2", "source": "ocr"},
            headers=headers,
        )
        response = self.client.post(
            "/demo/api/chat",
            json={
                "message": "确认",
                "source": "text",
                "pending_question": "1+1",
            },
            headers=headers,
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solving", payload["session_state"])
        self.assertEqual("旧题 x^2", payload["history_used"])

    def test_explicit_ocr_selection_overrides_stale_session_question(self):
        headers = {"X-Demo-Session": "test-explicit-ocr-selection-priority"}
        self.client.post(
            "/demo/api/chat",
            json={"message": "最后一题 x^2", "source": "ocr"},
            headers=headers,
        )
        response = self.client.post(
            "/demo/api/chat",
            json={
                "message": "确认",
                "source": "ocr",
                "pending_question": "1+1",
            },
            headers=headers,
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solving", payload["session_state"])
        self.assertEqual("1+1", payload["history_used"])

    def test_confirmation_uses_ocr_history_question_when_session_is_missing(self):
        response = self.client.post(
            "/demo/api/chat",
            json={
                "message": "确认，请开始",
                "source": "text",
                "history": [
                    {
                        "role": "user",
                        "text": "1+1\n请你确认题目识别是否正确。",
                    },
                ],
            },
            headers={"X-Demo-Session": "test-history-confirmation"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solving", payload["session_state"])
        self.assertEqual("1+1", payload["history_used"])

    def test_demo_ocr_rejects_unsupported_image_types(self):
        response = self.client.post(
            "/demo/api/ocr",
            data={"image": (io.BytesIO(b"not-an-image"), "question.pdf")},
            content_type="multipart/form-data",
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("仅支持", response.get_json()["detail"])

    def test_demo_ocr_reports_missing_coze_configuration(self):
        with (
            patch.object(demo_coze_ocr, "COZE_API_TOKEN", ""),
            patch.object(demo_coze_ocr, "COZE_BOT_ID", ""),
            patch.object(demo_coze_ocr, "COZE_OCR_WORKFLOW_ID", ""),
            patch.object(wsgi_app, "vision_ocr_configured", return_value=False),
            patch.object(demo_windows_ocr, "WINDOWS_OCR_FALLBACK", False),
        ):
            response = self.client.post(
                "/demo/api/ocr",
                data={
                    "image": (
                        io.BytesIO(b"\x89PNG\r\n\x1a\nquestion"),
                        "question.png",
                    )
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(503, response.status_code)
        detail = response.get_json()["detail"]
        self.assertIn("未配置", detail)
        self.assertNotIn("VISION_API", detail)

    def test_demo_ocr_uses_windows_fallback_when_coze_is_missing(self):
        with (
            patch.object(demo_coze_ocr, "COZE_API_TOKEN", ""),
            patch.object(demo_coze_ocr, "COZE_BOT_ID", ""),
            patch.object(demo_coze_ocr, "COZE_OCR_WORKFLOW_ID", ""),
            patch.object(wsgi_app, "vision_ocr_configured", return_value=False),
            patch.object(
                wsgi_app,
                "transcribe_windows_question_image",
                return_value="求导 x^2",
            ) as fallback,
        ):
            response = self.client.post(
                "/demo/api/ocr",
                data={
                    "image": (
                        io.BytesIO(b"\x89PNG\r\n\x1a\nquestion"),
                        "question.png",
                    )
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("求导 x^2", payload["text"])
        self.assertEqual("windows", payload["provider"])
        self.assertIn("离线 OCR", payload["warning"])
        fallback.assert_called_once()

    def test_demo_ocr_returns_question_text_when_coze_is_configured(self):
        with (
            patch.object(wsgi_app, "coze_ocr_configured", return_value=True),
            patch.object(wsgi_app, "vision_ocr_configured", return_value=False),
            patch.object(
                wsgi_app,
                "transcribe_question_image",
                return_value="求极限 lim x->0 sin(x)/x",
            ),
        ):
            response = self.client.post(
                "/demo/api/ocr",
                data={
                    "image": (
                        io.BytesIO(b"\x89PNG\r\n\x1a\nquestion"),
                        "question.png",
                    )
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            "求极限 lim x->0 sin(x)/x",
            response.get_json()["text"],
        )

    def test_demo_ocr_splits_multiple_questions_and_requires_selection(self):
        session_id = "test-multi-question-selection"
        demo_session.demo_sessions.reset(session_id)
        text = (
            "1. solve y' + y = 0\n"
            "2. solve y' + 2y = x\n"
            "3. compute lim x->0 sin(x)/x\n"
            "4. compute z = x^2 + y^2"
        )
        with (
            patch.object(wsgi_app, "coze_ocr_configured", return_value=True),
            patch.object(wsgi_app, "vision_ocr_configured", return_value=False),
            patch.object(
                wsgi_app,
                "transcribe_question_image",
                return_value=text,
            ),
        ):
            response = self.client.post(
                "/demo/api/ocr",
                data={
                    "image": (
                        io.BytesIO(b"\x89PNG\r\n\x1a\nquestion"),
                        "questions.png",
                    )
                },
                content_type="multipart/form-data",
                headers={"X-Demo-Session": session_id},
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(4, len(payload["question_blocks"]))
        self.assertTrue(payload["multiple_questions"])
        self.assertTrue(payload["selection_required"])
        self.assertFalse(payload["review_required"])
        self.assertFalse(payload["requires_confirmation"])
        self.assertEqual("awaiting_question_selection", payload["state"])
        session = demo_session.demo_sessions.get(session_id)
        self.assertEqual("waiting_image", session.state)
        self.assertEqual("", session.pending_question)

    def test_demo_ocr_audits_tall_image_when_only_one_question_is_returned(self):
        session_id = "test-tall-page-audit"
        demo_session.demo_sessions.reset(session_id)
        image_data = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            + struct.pack(">II", 1080, 2400)
        )
        with (
            patch.object(wsgi_app, "vision_ocr_configured", return_value=True),
            patch.object(
                wsgi_app,
                "transcribe_vision_question_image",
                return_value="4. compute the total differential of z=x^2+y^2",
            ),
            patch.object(
                wsgi_app,
                "audit_vision_question_count",
                return_value=4,
            ) as audit,
        ):
            response = self.client.post(
                "/demo/api/ocr",
                data={"image": (io.BytesIO(image_data), "page.png")},
                content_type="multipart/form-data",
                headers={"X-Demo-Session": session_id},
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(4, payload["audited_question_count"])
        self.assertTrue(payload["multiple_questions"])
        self.assertTrue(payload["selection_required"])
        self.assertTrue(payload["review_required"])
        self.assertEqual("awaiting_ocr_review", payload["state"])
        audit.assert_called_once()
        session = demo_session.demo_sessions.get(session_id)
        self.assertEqual("waiting_image", session.state)
        self.assertEqual("", session.pending_question)

    def test_question_block_detector_keeps_parenthesized_subparts_together(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "1. solve y' + y = 0\n"
            "2. solve y'' + y = 0\n"
            "(1) find the general solution\n"
            "(2) find y(0)=1"
        )

        self.assertEqual(2, len(blocks))
        self.assertEqual("1", blocks[0]["label"])
        self.assertEqual("2", blocks[1]["label"])
        self.assertIn("(2) find y(0)=1", blocks[1]["text"])

    def test_question_block_detector_ignores_scored_section_headings(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "二、填空题（每小题 3 分，共 24 分）.\n"
            "1. 直线 L1 与 L2 的夹角为____。\n"
            "2. 微分方程 y' + y = e^(-x)cosx 的通解为____。\n"
            "3. 函数 z = 1/2(x^2 + y^2) 在点 (1,1) 处减少最快的方向向量为____。\n"
            "4. 函数 z = ln(1 - x^2 + y^2) 在 x=1, y=2 时的全微分为____。"
        )

        self.assertEqual(4, len(blocks))
        self.assertEqual(["1", "2", "3", "4"], [
            block["label"] for block in blocks
        ])
        self.assertNotIn("填空题", blocks[0]["text"])

    def test_question_block_detector_ignores_other_section_headings(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "一、选择题（每小题 3 分，共 30 分）\n"
            "1. 下列函数连续的是____。\n"
            "2. 下列极限存在的是____。\n"
            "三、计算题（每小题 6 分，共 36 分）\n"
            "3. 求 lim x->0 sin(x)/x。\n"
            "4. 求 y' + y = 0 的通解。"
        )

        self.assertEqual(4, len(blocks))
        self.assertEqual(["1", "2", "3", "4"], [
            block["label"] for block in blocks
        ])
        self.assertTrue(all("选择题" not in block["text"] for block in blocks))
        self.assertTrue(all("计算题" not in block["text"] for block in blocks))

    def test_question_block_detector_splits_unpunctuated_ocr_numbering(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "二、填空题（每小题 3 分，共 24 分）\n"
            "1 直线 L1 与 L2 的夹角为____。\n"
            "2 微分方程 dy/dx+y=e^{-x}cosx 的通解为____。\n"
            "3 函数 z=1/2(x^2+y^2) 在点 (1,1) 处减少最快的方向向量为____。\n"
            "4 函数 z=ln(1-x^2+y^2) 在 x=1,y=2 时的全微分为____。"
        )

        self.assertEqual(4, len(blocks))
        self.assertEqual(
            ["1", "2", "3", "4"],
            [block["label"] for block in blocks],
        )
        self.assertTrue(blocks[0]["text"].startswith("1 直线"))
        self.assertNotIn("填空题", blocks[0]["text"])

    def test_question_block_detector_rejects_unpunctuated_arithmetic_lines(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "1 + 2\n"
            "2 + 3\n"
            "3 + 4"
        )

        self.assertEqual([], blocks)

    def test_question_block_detector_requires_consecutive_unpunctuated_numbers(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "1 求导 x^2\n"
            "3 求导 x^3"
        )

        self.assertEqual([], blocks)

    def test_question_block_detector_merges_mixed_ocr_numbering(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "1. 求导 x^2\n"
            "2 求导 x^3\n"
            "3. 求导 x^4"
        )

        self.assertEqual(3, len(blocks))
        self.assertEqual(["1", "2", "3"], [block["label"] for block in blocks])
        self.assertTrue(blocks[1]["text"].startswith("2 求导"))

    def test_question_block_detector_supports_ocr_punctuation_variants(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "1、直线 L1 与 L2 的夹角为____。\n"
            "2. 微分方程 y' + y = 0 的通解为____。\n"
            "3, 函数 z=x^2+y^2 的全微分为____。\n"
            "4：函数 z=ln(1+x^2+y^2) 的全微分为____。"
        )

        self.assertEqual(4, len(blocks))
        self.assertEqual(["1", "2", "3", "4"], [
            block["label"] for block in blocks
        ])

    def test_question_block_detector_merges_unpunctuated_and_ascii_numbering(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "1 直线 L1 与 L2 的夹角为____。\n"
            "2 微分方程 y' + y = 0 的通解为____。\n"
            "3, 函数 z=x^2+y^2 的全微分为____。\n"
            "4 函数 z=ln(1+x^2+y^2) 的全微分为____。"
        )

        self.assertEqual(4, len(blocks))
        self.assertEqual(["1", "2", "3", "4"], [
            block["label"] for block in blocks
        ])
        self.assertTrue(blocks[0]["text"].startswith("1 直线"))

    def test_question_block_detector_collapses_repeated_ocr_question_label(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "1 直线号:\n"
            "1 的夹角为____。\n"
            "2 ． 微分方程 y' + y = 0 的通解为____。\n"
            "3, 函数 z=x^2+y^2 的全微分为____。\n"
            "4 ． 函数 z=ln(1+x^2+y^2) 的全微分为____。"
        )

        self.assertEqual(4, len(blocks))
        self.assertEqual(["1", "2", "3", "4"], [
            block["label"] for block in blocks
        ])
        self.assertIn("的夹角", blocks[0]["text"])

    def test_question_block_detector_ignores_numbered_section_aliases(self):
        blocks = demo_question_blocks.extract_question_blocks(
            "第二题、填空题\n"
            "1. 求导 x^2\n"
            "第三题 计算题\n"
            "2. 求导 x^3"
        )

        self.assertEqual(2, len(blocks))
        self.assertEqual(["1", "2"], [block["label"] for block in blocks])
        self.assertTrue(
            all("填空题" not in block["text"] for block in blocks)
        )
        self.assertTrue(
            all("计算题" not in block["text"] for block in blocks)
        )

    def test_unpunctuated_question_number_prefix_is_removed(self):
        self.assertEqual(
            "微分方程 y'+y=0",
            demo_question_blocks.strip_question_number_prefix(
                "2 微分方程 y'+y=0"
            ),
        )
        self.assertEqual(
            "1 + 2",
            demo_question_blocks.strip_question_number_prefix("1 + 2"),
        )

    def test_question_number_prefix_stripper_preserves_math_content(self):
        cases = {
            "1. 1+1": "1+1",
            "第 2 题 求导 x^2": "求导 x^2",
            "3、积分 x^2": "积分 x^2",
            "1.5x+2": "1.5x+2",
            "二、填空题": "二、填空题",
            "1. 选择题": "1. 选择题",
            "2、计算题": "2、计算题",
            "(1) 求导 x^2": "(1) 求导 x^2",
        }

        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(
                    expected,
                    demo_question_blocks.strip_question_number_prefix(source),
                )

    def test_demo_ocr_uses_vision_and_caches_repeated_image(self):
        image_data = b"\x89PNG\r\n\x1a\nquestion"
        with (
            patch.object(wsgi_app, "vision_ocr_configured", return_value=True),
            patch.object(
                wsgi_app,
                "transcribe_vision_question_image",
                return_value="求导 f(x)=x^2（疑似 x）",
            ) as vision,
        ):
            first = self.client.post(
                "/demo/api/ocr",
                data={"image": (io.BytesIO(image_data), "question.png")},
                content_type="multipart/form-data",
            )
            second = self.client.post(
                "/demo/api/ocr",
                data={"image": (io.BytesIO(image_data), "question.png")},
                content_type="multipart/form-data",
            )

        self.assertEqual(200, first.status_code)
        first_payload = first.get_json()
        self.assertEqual("vision", first_payload["provider"])
        self.assertFalse(first_payload["cache_hit"])
        self.assertIsInstance(first_payload["elapsed_ms"], int)
        self.assertIn("疑似符号", first_payload["warning"])

        self.assertEqual(200, second.status_code)
        second_payload = second.get_json()
        self.assertTrue(second_payload["cache_hit"])
        self.assertEqual(first_payload["text"], second_payload["text"])
        vision.assert_called_once()

    def test_demo_ocr_removes_single_number_after_visual_audit(self):
        image_data = b"\x89PNG\r\n\x1a\nquestion"
        with (
            patch.object(wsgi_app, "vision_ocr_configured", return_value=True),
            patch.object(
                wsgi_app,
                "transcribe_vision_question_image",
                return_value="1. 2 + 2",
            ),
            patch.object(
                wsgi_app,
                "audit_vision_leading_question_number",
                return_value=False,
            ) as audit_number,
        ):
            response = self.client.post(
                "/demo/api/ocr",
                data={"image": (io.BytesIO(image_data), "question.png")},
                content_type="multipart/form-data",
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("2 + 2", payload["text"])
        self.assertEqual("awaiting_ocr_confirmation", payload["state"])
        audit_number.assert_called_once_with(image_data, "image/png")

    def test_demo_ocr_preserves_single_number_when_visual_audit_finds_it(self):
        image_data = b"\x89PNG\r\n\x1a\nquestion"
        with (
            patch.object(wsgi_app, "vision_ocr_configured", return_value=True),
            patch.object(
                wsgi_app,
                "transcribe_vision_question_image",
                return_value="1. 2 + 2",
            ),
            patch.object(
                wsgi_app,
                "audit_vision_leading_question_number",
                return_value=True,
            ),
        ):
            response = self.client.post(
                "/demo/api/ocr",
                data={"image": (io.BytesIO(image_data), "question.png")},
                content_type="multipart/form-data",
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("1. 2 + 2", response.get_json()["text"])

    def test_demo_ocr_falls_back_to_coze_when_vision_fails(self):
        with (
            patch.object(wsgi_app, "coze_ocr_configured", return_value=True),
            patch.object(wsgi_app, "vision_ocr_configured", return_value=True),
            patch.object(
                wsgi_app,
                "transcribe_vision_question_image",
                side_effect=demo_vision.VisionUpstreamError(
                    "直连视觉识别失败。"
                ),
            ),
            patch.object(
                wsgi_app,
                "transcribe_question_image",
                return_value="求极限 lim x->0 sin(x)/x",
            ),
        ):
            response = self.client.post(
                "/demo/api/ocr",
                data={
                    "image": (
                        io.BytesIO(b"\x89PNG\r\n\x1a\nquestion"),
                        "question.png",
                    )
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("coze", response.get_json()["provider"])

    def test_coze_ocr_adapter_runs_upload_chat_poll_and_message_steps(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

        with (
            patch.object(demo_coze_ocr, "COZE_API_BASE", "https://coze.test"),
            patch.object(demo_coze_ocr, "COZE_API_TOKEN", "test-token"),
            patch.object(demo_coze_ocr, "COZE_BOT_ID", "test-bot"),
            patch.object(demo_coze_ocr, "COZE_OCR_WORKFLOW_ID", ""),
            patch.object(demo_coze_ocr, "COZE_POLL_INTERVAL_SECONDS", 0),
            patch.object(
                demo_coze_ocr,
                "urlopen",
                side_effect=[
                    FakeResponse({"code": 0, "data": {"id": "file-1"}}),
                    FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                "id": "chat-1",
                                "conversation_id": "conversation-1",
                                "status": "in_progress",
                            },
                        }
                    ),
                    FakeResponse({"code": 0, "data": {"status": "completed"}}),
                    FakeResponse(
                        {
                            "code": 0,
                            "data": [
                                {
                                    "role": "assistant",
                                    "type": "answer",
                                    "content_type": "text",
                                    "content": (
                                        "求极限 lim x->0 sin(x)/x\n\n"
                                        "请确认识别是否正确，再继续帮我解题。"
                                    ),
                                }
                            ],
                        }
                    ),
                ],
            ) as urlopen_mock,
        ):
            text = demo_coze_ocr.transcribe_question_image(
                b"\x89PNG\r\n\x1a\nquestion",
                "image/png",
            )

        self.assertEqual("求极限 lim x->0 sin(x)/x", text)
        requests = [call.args[0] for call in urlopen_mock.call_args_list]
        self.assertTrue(requests[0].full_url.endswith("/v1/files/upload"))
        self.assertTrue(requests[1].full_url.endswith("/v3/chat"))
        self.assertIn("/v3/chat/retrieve?", requests[2].full_url)
        self.assertIn("/v3/chat/message/list?", requests[3].full_url)
        for request_call in urlopen_mock.call_args_list:
            request_timeout = request_call.kwargs["timeout"]
            self.assertGreater(request_timeout, 0)
            self.assertLessEqual(
                request_timeout,
                demo_coze_ocr.COZE_TIMEOUT_SECONDS,
            )
        chat_payload = json.loads(requests[1].data)
        additional_messages = chat_payload["additional_messages"]
        self.assertEqual(
            "object_string",
            additional_messages[0]["content_type"],
        )
        content = json.loads(additional_messages[0]["content"])
        self.assertEqual("file-1", content[1]["file_id"])
        self.assertIn("OCR / Image2text", content[0]["text"])
        self.assertIn("轻微模糊", content[0]["text"])
        self.assertIn("疑似", content[0]["text"])
        self.assertIn("0 与字母 O/o", content[0]["text"])
        self.assertIn("按题号逐题分行", content[0]["text"])
        self.assertIn("不得合并", content[0]["text"])

    def test_coze_ocr_workflow_runs_upload_and_workflow_without_bot_chat(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

        with (
            patch.object(demo_coze_ocr, "COZE_API_BASE", "https://coze.test"),
            patch.object(demo_coze_ocr, "COZE_API_TOKEN", "test-token"),
            patch.object(demo_coze_ocr, "COZE_BOT_ID", "test-bot"),
            patch.object(
                demo_coze_ocr,
                "COZE_OCR_WORKFLOW_ID",
                "workflow-1",
            ),
            patch.object(
                demo_coze_ocr,
                "COZE_OCR_IMAGE_PARAMETER",
                "question_image",
            ),
            patch.object(
                demo_coze_ocr,
                "COZE_OCR_IMAGE_PARAMETER_FORMAT",
                "file_id",
            ),
            patch.object(demo_coze_ocr, "COZE_OCR_OUTPUT_FIELD", "ocr_text"),
            patch.object(
                demo_coze_ocr,
                "urlopen",
                side_effect=[
                    FakeResponse({"code": 0, "data": {"id": "file-1"}}),
                    FakeResponse(
                        {
                            "code": 0,
                            "data": (
                                '{"ocr_text":"求导 f(x)=x^2\\n\\n'
                                '请确认识别是否正确，再继续帮我解题。"}'
                            ),
                        }
                    ),
                ],
            ) as urlopen_mock,
        ):
            text = demo_coze_ocr.transcribe_question_image(
                b"\x89PNG\r\n\x1a\nquestion",
                "image/png",
            )

        self.assertEqual("求导 f(x)=x^2", text)
        requests = [call.args[0] for call in urlopen_mock.call_args_list]
        self.assertEqual(2, len(requests))
        self.assertTrue(requests[0].full_url.endswith("/v1/files/upload"))
        self.assertTrue(requests[1].full_url.endswith("/v1/workflow/run"))
        workflow_payload = json.loads(requests[1].data)
        self.assertEqual("workflow-1", workflow_payload["workflow_id"])
        self.assertEqual(
            "file-1",
            workflow_payload["parameters"]["question_image"],
        )
        self.assertFalse(workflow_payload["is_async"])
        self.assertNotIn("bot_id", workflow_payload)

    def test_coze_ocr_workflow_falls_back_to_bot_when_needed(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

        with (
            patch.object(demo_coze_ocr, "COZE_API_BASE", "https://coze.test"),
            patch.object(demo_coze_ocr, "COZE_API_TOKEN", "test-token"),
            patch.object(demo_coze_ocr, "COZE_BOT_ID", "test-bot"),
            patch.object(
                demo_coze_ocr,
                "COZE_OCR_WORKFLOW_ID",
                "workflow-1",
            ),
            patch.object(demo_coze_ocr, "COZE_POLL_INTERVAL_SECONDS", 0),
            patch.object(
                demo_coze_ocr,
                "urlopen",
                side_effect=[
                    FakeResponse({"code": 0, "data": {"id": "file-1"}}),
                    FakeResponse({"code": 4200, "msg": "workflow failed"}),
                    FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                "id": "chat-1",
                                "conversation_id": "conversation-1",
                                "status": "in_progress",
                            },
                        }
                    ),
                    FakeResponse({"code": 0, "data": {"status": "completed"}}),
                    FakeResponse(
                        {
                            "code": 0,
                            "data": [
                                {
                                    "role": "assistant",
                                    "type": "answer",
                                    "content": "求极限 lim x->0 sin(x)/x",
                                }
                            ],
                        }
                    ),
                ],
            ) as urlopen_mock,
        ):
            text = demo_coze_ocr.transcribe_question_image(
                b"\x89PNG\r\n\x1a\nquestion",
                "image/png",
            )

        self.assertEqual("求极限 lim x->0 sin(x)/x", text)
        requests = [call.args[0] for call in urlopen_mock.call_args_list]
        self.assertEqual(5, len(requests))
        self.assertTrue(requests[1].full_url.endswith("/v1/workflow/run"))
        self.assertTrue(requests[2].full_url.endswith("/v3/chat"))
        chat_payload = json.loads(requests[2].data)
        content = json.loads(chat_payload["additional_messages"][0]["content"])
        self.assertEqual("file-1", content[1]["file_id"])

    def test_coze_ocr_polling_starts_faster_than_configured_cap(self):
        with patch.object(
            demo_coze_ocr,
            "COZE_POLL_INTERVAL_SECONDS",
            0.8,
        ):
            self.assertEqual(0.15, demo_coze_ocr._poll_delay(0))
            self.assertEqual(0.3, demo_coze_ocr._poll_delay(1))
            self.assertEqual(0.5, demo_coze_ocr._poll_delay(2))
            self.assertEqual(0.8, demo_coze_ocr._poll_delay(3))

    def test_math_text_normalization_handles_common_ocr_notation(self):
        cases = (
            ("x\u00b2", "x^2"),
            ("x\u2081", "x_1"),
            ("\u221a2", "sqrt(2)"),
            ("\u221a2x", "sqrt(2)*x"),
            ("\u221ax", "sqrt(x)"),
            ("\u221a(x+1)", "sqrt(x+1)"),
            ("y=-2\u221a2x+2", "y=-2sqrt(2)*x+2"),
            ("x\u21920", "x->0"),
            ("\u03c0", "pi"),
            ("\u221e", "oo"),
            (r"\frac{a+b}{c}", "((a+b)/(c))"),
        )

        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    expected,
                    demo_math_text.normalize_math_text(source),
                )

    def test_all_ocr_cleaners_normalize_math_notation(self):
        source = "x\u00b2 + \u221ay"
        expected = "x^2 + sqrt(y)"

        self.assertEqual(expected, demo_coze_ocr._clean_transcription(source))
        self.assertEqual(expected, demo_vision._clean_transcription(source))
        self.assertEqual(expected, demo_windows_ocr._normalize_ocr_text(source))
        self.assertEqual(expected, demo_chat._normalize_text(source))

    def test_direct_vision_adapter_sends_image_and_uses_finite_timeout(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "求导 f(x)=x^2",
                                }
                            }
                        ]
                    },
                    ensure_ascii=False,
                ).encode("utf-8")

        with (
            patch.object(demo_vision, "VISION_API_URL", "https://vision.test/chat"),
            patch.object(demo_vision, "VISION_API_KEY", "vision-token"),
            patch.object(demo_vision, "VISION_MODEL", "vision-model"),
            patch.object(demo_vision, "VISION_TIMEOUT_SECONDS", 30),
            patch.object(
                demo_vision,
                "urlopen",
                return_value=FakeResponse(),
            ) as vision_urlopen,
        ):
            text = demo_vision.transcribe_question_image(
                b"\x89PNG\r\n\x1a\nquestion",
                "image/png",
                timeout_seconds=12.5,
            )

        self.assertEqual("求导 f(x)=x^2", text)
        request = vision_urlopen.call_args.args[0]
        self.assertEqual("https://vision.test/chat", request.full_url)
        self.assertEqual(12.5, vision_urlopen.call_args.kwargs["timeout"])
        payload = json.loads(request.data)
        self.assertEqual("vision-model", payload["model"])
        prompt = payload["messages"][0]["content"][0]["text"]
        self.assertIn("基础算术", prompt)
        self.assertIn("不要因为题目简单", prompt)
        self.assertIn("逐题", prompt)
        self.assertIn("不得合并", prompt)
        self.assertIn("题号必须与后面的算式或文字用空格隔开", prompt)
        self.assertIn("不得写成「10.2 + 2」", prompt)
        self.assertIn("禁止自行添加任何编号、序号或前缀", prompt)
        self.assertNotIn("1. 2 + 2", prompt)
        self.assertIn("data:image/png;base64,", payload["messages"][0]["content"][1]["image_url"]["url"])
        prompt = payload["messages"][0]["content"][0]["text"]
        self.assertIn("数字 0 与字母 O/o", prompt)
        self.assertIn("疑似", prompt)

    def test_direct_vision_adapter_sends_remote_image_url(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "∫ x^2 dx",
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        with (
            patch.object(demo_vision, "VISION_API_URL", "https://vision.test/chat"),
            patch.object(demo_vision, "VISION_API_KEY", "vision-token"),
            patch.object(demo_vision, "VISION_MODEL", "vision-model"),
            patch.object(
                demo_vision,
                "urlopen",
                return_value=FakeResponse(),
            ) as vision_urlopen,
        ):
            text = demo_vision.transcribe_question_image_url(
                "https://images.example/question.png"
            )

        self.assertEqual("∫ x^2 dx", text)
        request = vision_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        image_reference = payload["messages"][0]["content"][1]["image_url"]["url"]
        self.assertEqual("https://images.example/question.png", image_reference)

    def test_coze_ocr_prompt_accepts_basic_arithmetic(self):
        self.assertIn("基础算术", demo_coze_ocr.COZE_OCR_PROMPT)
        self.assertIn("不要因为题目简单", demo_coze_ocr.COZE_OCR_PROMPT)
        self.assertIn(
            "题号必须与后面的算式或文字用空格隔开",
            demo_coze_ocr.COZE_OCR_PROMPT,
        )
        self.assertIn("不得写成「10.2 + 2」", demo_coze_ocr.COZE_OCR_PROMPT)
        self.assertIn(
            "禁止自行添加任何编号、序号或前缀",
            demo_coze_ocr.COZE_OCR_PROMPT,
        )
        self.assertNotIn("1. 2 + 2", demo_coze_ocr.COZE_OCR_PROMPT)

    def test_direct_vision_adapter_distinguishes_http_failures(self):
        cases = (
            (400, "参数无效"),
            (401, "鉴权失败"),
            (403, "免费额度"),
            (429, "请求过于频繁"),
        )

        for status_code, expected_message in cases:
            with self.subTest(status_code=status_code):
                error = HTTPError(
                    "https://vision.test/chat",
                    status_code,
                    "vision failure",
                    {},
                    None,
                )
                with (
                    patch.object(
                        demo_vision,
                        "VISION_API_URL",
                        "https://vision.test/chat",
                    ),
                    patch.object(demo_vision, "VISION_API_KEY", "vision-token"),
                    patch.object(demo_vision, "VISION_MODEL", "vision-model"),
                    patch.object(demo_vision, "urlopen", side_effect=error),
                ):
                    with self.assertRaises(
                        demo_vision.VisionUpstreamError
                    ) as raised:
                        demo_vision.transcribe_question_image(
                            b"\x89PNG\r\n\x1a\nquestion",
                            "image/png",
                        )

                self.assertIn(expected_message, str(raised.exception))

    def test_direct_vision_adapter_builds_chat_endpoint_from_base_url(self):
        with (
            patch.object(demo_vision, "VISION_API_URL", ""),
            patch.object(
                demo_vision,
                "VISION_API_BASE",
                "https://dashscope.aliyuncs.com/compatible-mode/v1/",
            ),
        ):
            self.assertEqual(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                demo_vision._vision_chat_endpoint(),
            )

        with patch.object(
            demo_vision,
            "VISION_API_URL",
            "https://vision.test/custom-chat",
        ):
            self.assertEqual(
                "https://vision.test/custom-chat",
                demo_vision._vision_chat_endpoint(),
            )

    def test_missing_route_returns_json_404(self):
        response = self.client.get("/not-found")

        self.assertEqual(404, response.status_code)
        self.assertIn("not found", response.get_json()["detail"].lower())

    def test_demo_calculates_derivative(self):
        response = self.client.post(
            "/demo/api/verify",
            json={"expression": "x^2", "variable": "x", "candidate": "2x"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("2*x", payload["derivative"])
        self.assertIs(True, payload["is_correct"])

    def test_demo_calculates_definite_integral(self):
        response = self.client.post(
            "/demo/api/integrate",
            json={
                "expression": "x^2",
                "variable": "x",
                "lower": "0",
                "upper": "1",
                "candidate": "1/3",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("1/3", payload["integral"])
        self.assertIs(True, payload["is_correct"])

    def test_demo_calculates_limit(self):
        response = self.client.post(
            "/demo/api/limit",
            json={
                "expression": "sin(x)/x",
                "variable": "x",
                "point": "0",
                "candidate": "1",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("1", payload["limit"])
        self.assertIs(True, payload["is_correct"])

    def test_demo_knowledge_accepts_coze_query_parameters(self):
        response = self.client.post(
            "/demo/api/knowledge",
            query_string={
                "query": "定积分的定义",
                "limit": "3",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("定积分的定义", payload["query"])
        self.assertEqual("knowledge/05_定积分.md", payload["results"][0]["source"])

    def test_query_optional_fields_accept_coze_blank_strings(self):
        cases = (
            (
                "/verify-query",
                {"expression": "x的平方", "variable": "", "candidate": ""},
            ),
            (
                "/integrate-query",
                {
                    "expression": "根号下x",
                    "variable": "",
                    "lower": "",
                    "upper": "",
                    "candidate": "",
                },
            ),
            (
                "/limit-query",
                {
                    "expression": "sinx除以x",
                    "variable": "",
                    "point": "",
                    "direction": "",
                    "candidate": "",
                },
            ),
        )
        for path, params in cases:
            with self.subTest(path=path):
                response = self.client.post(path, query_string=params)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertIsNone(payload["candidate"])
                self.assertIsNone(payload["is_correct"])

        plot = self.client.post(
            "/plot-query",
            query_string={
                "expression": "sinx",
                "variable": "",
                "x_min": "",
                "x_max": "",
                "y_min": "",
                "y_max": "",
                "samples": "",
                "width": "",
                "height": "",
            },
        )

        self.assertEqual(200, plot.status_code)
        plot_payload = plot.get_json()
        self.assertEqual("sin(x)", plot_payload["expression"])
        self.assertEqual("x", plot_payload["variable"])
        self.assertIn("<svg", plot_payload["svg"])

    def test_demo_calculates_extended_chapter_solve(self):
        response = self.client.post(
            "/demo/api/solve",
            json={
                "chapter": "series",
                "topic": "sum",
                "inputs": {
                    "expression": "1/n^2",
                    "variable": "n",
                    "lower": 1,
                    "upper": "oo",
                },
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("pi**2/6", payload["result"])

    def test_demo_generates_function_plot(self):
        response = self.client.post(
            "/demo/api/plot",
            json={"expression": "sin(x)", "x_min": -3, "x_max": 3},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("sin(x)", payload["expression"])
        self.assertIn("<svg", payload["svg"])
        self.assertIn('stroke="#2868d8"', payload["svg"])

    def test_demo_serves_function_plot_as_svg(self):
        response = self.client.get(
            "/demo/api/plot.svg",
            query_string={"expression": "x^2", "x_min": -2, "x_max": 2},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("image/svg+xml", response.mimetype)
        self.assertIn("<svg", response.get_data(as_text=True))

    def test_demo_chat_returns_function_plot(self):
        response = self.chat("画函数 y=sin(x)，x 从 -3 到 3")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("plot", payload["intent"])
        self.assertEqual("sin(x)", payload["calculation"]["expression"])

        plot_url = payload["calculation"]["plot_url"]
        self.assertIn("/demo/api/plot.svg?", plot_url)

        image = self.client.get(plot_url)
        self.assertEqual(200, image.status_code)
        self.assertEqual("image/svg+xml", image.mimetype)
        self.assertIn("<svg", image.get_data(as_text=True))

    def test_demo_chat_solves_derivative_and_integral_applications(self):
        cases = (
            (
                "求切线 y=x^2 在 x=1 处",
                "切线方程",
                "Eq(y, 2*x - 1)",
            ),
            (
                "求极值 x^2-2x",
                "极值判定",
                None,
            ),
            (
                "求单调区间 x^2-2x",
                "单调区间分析",
                None,
            ),
            (
                "求曲线 y=x^2 与 x 轴在 0 到 1 之间围成的面积",
                "平面图形面积",
                "1/3",
            ),
            (
                "求曲线 y=x 绕 x 轴旋转一周所得旋转体体积，x 从 0 到 1",
                "旋转体体积（绕x轴）",
                "pi/3",
            ),
            (
                "求曲线 y=(2/3)x^(3/2) 从 x=0 到 x=1 的弧长",
                "平面曲线弧长",
                "-2/3 + 4*sqrt(2)/3",
            ),
        )
        for message, method, result in cases:
            with self.subTest(message=message):
                response = self.chat(message)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("solve", payload["intent"])
                self.assertEqual(method, payload["calculation"]["method"])
                if result is not None:
                    self.assertEqual(result, payload["calculation"]["result"])
                self.assertIn("**题目理解**", payload["reply"])
                self.assertIn("**最终答案**", payload["reply"])

    def test_demo_chat_solves_series_convergence(self):
        cases = (
            ("判断级数 1/n^2 收敛", "收敛"),
            ("判断级数 n^2 收敛", "发散"),
        )
        for message, expected in cases:
            with self.subTest(message=message):
                response = self.chat(message)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("solve", payload["intent"])
                self.assertEqual(expected, payload["calculation"]["result"])

    def test_demo_chat_solves_multiple_integrals(self):
        response = self.chat("积分 0 到 1 0 到 1 x*y")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("1/4", payload["calculation"]["result"])

        triple = self.chat("三重积分 x+y+z 变量 x,y,z")
        self.assertEqual("solve", triple.get_json()["intent"])
        self.assertEqual("3/2", triple.get_json()["calculation"]["result"])

    def test_demo_chat_solves_polar_double_integral(self):
        response = self.chat(
            "极坐标二重积分 x^2+y^2 r 0 到 1 theta 0 到 2*pi"
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("pi/2", payload["calculation"]["result"])
        self.assertEqual("二重积分（极坐标）", payload["calculation"]["method"])

    def test_demo_chat_solves_coordinate_triple_integrals(self):
        cylindrical = self.chat(
            "柱面坐标三重积分 x^2+y^2 r 0 到 1 theta 0 到 2*pi z 0 到 1"
        )

        self.assertEqual(200, cylindrical.status_code)
        payload = cylindrical.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("pi/2", payload["calculation"]["result"])
        self.assertEqual("三重积分（柱面坐标）", payload["calculation"]["method"])

        spherical = self.chat(
            "球面坐标三重积分 1 rho 0 到 1 phi 0 到 pi theta 0 到 2*pi"
        )

        self.assertEqual(200, spherical.status_code)
        payload = spherical.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("4*pi/3", payload["calculation"]["result"])
        self.assertEqual("三重积分（球面坐标）", payload["calculation"]["method"])

    def test_demo_chat_solves_explicit_curve_and_surface_integrals(self):
        cases = (
            (
                "第一类曲线积分 x+y 沿曲线 y=x，x 从 0 到 1",
                "第一类曲线积分（显式曲线）",
                "sqrt(2)",
            ),
            (
                "第二类曲线积分 向量场(x,y) 沿曲线 y=x，x 从 0 到 1",
                "第二类曲线积分（显式曲线）",
                "1",
            ),
            (
                "第一类曲面积分 1 在曲面 z=x，x 从 0 到 1，y 从 0 到 1",
                "第一类曲面积分（显式曲面）",
                "sqrt(2)",
            ),
            (
                "第二类曲面积分 向量场(0,0,1) 在曲面 z=x，x 从 0 到 1，y 从 0 到 1",
                "第二类曲面积分（显式曲面）",
                "1",
            ),
        )
        for message, method, expected in cases:
            with self.subTest(message=message):
                response = self.chat(message)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("solve", payload["intent"])
                calculation = payload["calculation"]
                self.assertEqual(method, calculation["method"])
                self.assertEqual(expected, calculation["result"])
                headings = (
                    "题目理解",
                    "解题思路",
                    "详细计算步骤",
                    "最终答案",
                )
                positions = [
                    payload["reply"].index(heading)
                    for heading in headings
                ]
                self.assertEqual(sorted(positions), positions)

    def test_demo_chat_solves_differential_equation(self):
        response = self.chat("解微分方程 y'-y=0")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertIn("C1*exp(x)", payload["calculation"]["result"])

    def test_demo_chat_cleans_ocr_differential_equation_question(self):
        response = self.chat(
            "微分方程 dy/dx + y = e^(-x) cos x 的通解为____。"
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertIn(
            "(C1 + sin(x))*exp(-x)",
            payload["calculation"]["result"],
        )

    def test_demo_chat_cleans_ocr_heading_and_confirmation_tail(self):
        for message in (
            "二、填空题 微分方程 y' + y = e^(-x) cos x 的通解为____。 。",
            (
                "y' + y = e^(-x) cos x 的通解为______。 "
                "确认无误回复“确认”，我将开始计算。"
            ),
            "求解：y' + y = e^(-x) cos x",
        ):
            with self.subTest(message=message):
                response = self.chat(message)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("solve", payload["intent"])
                self.assertIn(
                    "(C1 + sin(x))*exp(-x)",
                    payload["calculation"]["result"],
                )

        response = self.chat("解 y'-y=0")
        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertIn("C1*exp(x)", payload["calculation"]["result"])

    def test_demo_chat_normalizes_ocr_differential_equation_variants(self):
        cases = (
            (
                "微分方程 y′ + y = e^{-x} cos2x 的通解",
                "sin(2*x)/2",
            ),
            (
                "微分方程 y′ + y = e^(-x) sin 2x 的通解",
                "cos(2*x)/2",
            ),
            (
                "求解微分方程 (dy)/(dx) + 2y = e^(-x)",
                "C1*exp(-x)",
            ),
            (
                "微分方程 y″ + 4y = sin2x 的通解",
                "sin(2*x)",
            ),
            (
                "微分方程 xy′ + y = x² 的通解",
                "C1 + x**3/3",
            ),
            (
                "d/dx y + y = cos x",
                "sin(x)/2",
            ),
            (
                "微分方程 y'(t)+y(t)=t 的通解",
                "C1*exp(-t)",
            ),
            (
                r"微分方程 y^{\prime}+y=e^{-x}\cos x 的通解",
                "(C1 + sin(x))*exp(-x)",
            ),
        )

        for message, expected in cases:
            with self.subTest(message=message):
                response = self.chat(message)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("solve", payload["intent"])
                self.assertIn(expected, payload["calculation"]["result"])

    def test_demo_chat_solves_parametric_derivative(self):
        response = self.chat("参数方程 x=t^2, y=t^3 求 dy/dx")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("3*t/2", payload["calculation"]["result"])

    def test_demo_chat_solves_system_implicit_derivative(self):
        response = self.chat(
            "方程组 u+v=x; u-v=y，因变量 u,v，自变量 x，求 ∂u/∂x"
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("1/2", payload["calculation"]["result"])

    def test_demo_chat_solves_conditional_extrema(self):
        response = self.chat("条件极值 x*y 约束 x+y=1 变量 x,y")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual(
            "条件极值（拉格朗日乘数法）",
            payload["calculation"]["method"],
        )
        self.assertIn("x: 1/2", payload["calculation"]["result"])
        self.assertIn("'kind': '极大值'", payload["calculation"]["result"])

    def test_demo_chat_solves_conditional_extrema_with_multiple_constraints(self):
        response = self.chat(
            "条件极值 x^2+y^2+z^2 约束 x=0; y=0 变量 x,y,z"
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual(
            "条件极值（拉格朗日乘数法）",
            payload["calculation"]["method"],
        )
        self.assertIn("lambda1: 0", payload["calculation"]["result"])
        self.assertIn("'kind': '极小值'", payload["calculation"]["result"])

    def test_demo_chat_solves_vector_dot_product(self):
        response = self.chat("向量 (1,2,3) 点乘 (4,5,6)")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("32", payload["calculation"]["result"])

    def test_demo_chat_calculates_derivative(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "求导 x^2"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertEqual("verify", payload["intent"])
        self.assertEqual("2*x", payload["calculation"]["derivative"])
        self.assertIsNone(payload["calculation"]["is_correct"])
        self.assertIn(r"\frac{d}{dx}", payload["formula_latex"])

    def test_demo_chat_checks_derivative_candidate(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "判断 2x 是不是 x^2 的导数"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("verify", payload["intent"])
        self.assertIs(True, payload["calculation"]["is_correct"])
        self.assertIn("这个答案是对的", payload["reply"])

    def test_demo_chat_calculates_english_derivative_commands(self):
        cases = (
            ("derivative x^3", "x", "3*x**2"),
            ("differentiate x^3", "x", "3*x**2"),
            (
                "find the derivative of t^3 with respect to t",
                "t",
                "3*t**2",
            ),
        )

        for message, variable, derivative in cases:
            with self.subTest(message=message):
                response = self.chat(message)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("verify", payload["intent"])
                self.assertEqual(derivative, payload["calculation"]["derivative"])
                self.assertEqual(variable, payload["calculation"]["variable"])
                self.assertIsNone(payload["calculation"]["candidate"])

        response = self.chat("is 2*x the derivative of x^2")
        payload = response.get_json()
        self.assertEqual("verify", payload["intent"])
        self.assertIs(True, payload["calculation"]["is_correct"])

    def test_demo_chat_calculates_indefinite_integral(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "积分 x^2"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("integrate", payload["intent"])
        self.assertEqual("x**3/3", payload["calculation"]["integral"])
        self.assertIn("+C", payload["formula_latex"])

    def test_demo_chat_calculates_definite_integral(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "积分 0 到 1 x^2"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("integrate", payload["intent"])
        self.assertEqual("1/3", payload["calculation"]["integral"])
        self.assertIn(r"\int_{0}^{1}", payload["formula_latex"])

    def test_demo_chat_calculates_english_integral_commands(self):
        cases = (
            ("integral x^2 dx", "x", "x**3/3"),
            ("integrate x^2", "x", "x**3/3"),
            ("antiderivative of x^2", "x", "x**3/3"),
            ("integral of t^2 dt with respect to t", "t", "t**3/3"),
        )

        for message, variable, integral in cases:
            with self.subTest(message=message):
                response = self.chat(message)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("integrate", payload["intent"])
                self.assertEqual(integral, payload["calculation"]["integral"])
                self.assertEqual(variable, payload["calculation"]["variable"])
                self.assertIsNone(payload["calculation"]["candidate"])

        for message in (
            "integral of x^2 from 0 to 1",
            "evaluate the definite integral from 0 to 1 of x^2 dx",
        ):
            with self.subTest(message=message):
                payload = self.chat(message).get_json()
                self.assertEqual("integrate", payload["intent"])
                self.assertEqual("1/3", payload["calculation"]["integral"])

    def test_demo_chat_keeps_english_concepts_out_of_solver(self):
        with patch.object(demo_chat, "GENERAL_CHAT_API_KEY", ""):
            for message in ("what is a derivative", "what is an integral"):
                with self.subTest(message=message):
                    payload = self.chat(message).get_json()
                    self.assertNotIn(payload["intent"], {"verify", "integrate"})
                    self.assertIsNone(payload["calculation"])

    def test_demo_chat_solves_interval_extrema(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "求函数 f(x)=x^2-4x+3 在 [0,5] 上的最大值"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("solve", payload["intent"])
        self.assertEqual("最大值", payload["calculation"]["kind"])
        self.assertEqual("[0, 5]", payload["calculation"]["interval"])
        self.assertEqual("2", payload["calculation"]["critical_points"][0])
        self.assertEqual("8", payload["calculation"]["result"])
        self.assertNotIn("*", payload["reply"])
        self.assertIn("$f'(x)=", payload["reply"])
        self.assertIn("$f(x)=-1$", payload["reply"])

    def test_demo_chat_verifies_parametric_tangent_normal_positive_case(self):
        question = (
            "求曲线 {x = sin(t), y = cos(2*t)} 在当 t = pi/4 "
            "处的切线方程和法线方程。"
        )

        response = self.chat(question, session="p0-parametric-positive")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertEqual("solve", payload["intent"])
        self.assertIs(True, payload["verified"])
        self.assertIs(True, payload["verification"]["passed"])
        self.assertGreaterEqual(len(payload["verification"]["checks"]), 5)
        self.assertTrue(
            all(
                check["passed"] is True
                for check in payload["verification"]["checks"]
            )
        )
        self.assertEqual(
            "parametric_tangent_normal",
            payload["verification"]["kind"],
        )
        self.assertEqual(
            "parametric_tangent_normal",
            payload["calculation"]["topic"],
        )
        self.assertIn("(sqrt(2)/2, 0)", payload["calculation"]["result"])
        self.assertIn(
            "y = -2*sqrt(2)*x + 2",
            payload["calculation"]["result"],
        )
        self.assertIn(
            "y = sqrt(2)*x/4 - 1/4",
            payload["calculation"]["result"],
        )
        self.assertEqual(4, len(payload["knowledge_points"]))

    def test_demo_chat_six_missing_condition_cases_are_blocked(self):
        questions = (
            "求参数方程 x=sin(t), y=cos(2t) 的切线方程和法线方程",
            "求函数的极值",
            "求函数的最大值",
            "求积分",
            "求微分方程的通解",
            "求极限",
        )
        general_success = {
            "status": "ok",
            "intent": "general",
            "reply": "这是不应出现的通用模型成功回答。",
            "formula_latex": "",
            "formula_text": "",
            "calculation": None,
        }

        with patch.object(
            demo_chat,
            "_build_general_chat_response",
            return_value=general_success,
        ) as general_chat:
            responses = [
                self.chat(question, session=f"p0-negative-{index}")
                for index, question in enumerate(questions, start=1)
            ]

        self.assertEqual(6, len(responses))
        for question, response in zip(questions, responses):
            with self.subTest(question=question):
                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertNotEqual("ok", payload["status"])
                self.assertIsNone(payload["calculation"])
                self.assertIsNot(True, payload.get("verified"))
                self.assertFalse(payload.get("knowledge_points") or [])
                self.assertNotIn("**最终答案**", payload["reply"])
        general_chat.assert_not_called()

    def test_demo_teaching_blocks_all_six_missing_condition_cases(self):
        questions = (
            "求参数方程 x=sin(t), y=cos(2t) 的切线方程和法线方程",
            "求函数的极值",
            "求函数的最大值",
            "求积分",
            "求微分方程的通解",
            "求极限",
        )

        for index, question in enumerate(questions, start=1):
            with self.subTest(question=question):
                response = self.chat(
                    question,
                    session=f"p0-teaching-negative-{index}",
                    mode="teach",
                )

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("error", payload["status"])
                self.assertIn(
                    payload["intent"],
                    {"teaching_failed", "teaching_unavailable"},
                )
                self.assertIsNone(payload["calculation"])
                self.assertNotIn("teaching", payload)
                self.assertFalse(payload.get("knowledge_points") or [])
                self.assertNotIn("**最终答案**", payload["reply"])

    def test_demo_chat_repeated_submissions_are_stable_across_sessions(self):
        question = (
            "求曲线 {x = sin(t), y = cos(2*t)} 在当 t = pi/4 "
            "处的切线方程和法线方程。"
        )
        payloads = []
        for index in range(1, 6):
            response = self.chat(
                question,
                session=f"p0-repeat-across-{index}",
            )
            self.assertEqual(200, response.status_code)
            payloads.append(response.get_json())

        baseline = payloads[0]
        self.assertEqual("ok", baseline["status"])
        self.assertIs(True, baseline["verified"])
        for payload in payloads[1:]:
            self.assertEqual(baseline["calculation"], payload["calculation"])
            self.assertEqual(baseline["reply"], payload["reply"])
            self.assertEqual(
                baseline["verification"],
                payload["verification"],
            )
            self.assertEqual(
                baseline["knowledge_points"],
                payload["knowledge_points"],
            )

    def test_demo_chat_ocr_confirmation_matches_manual_parametric_solution(
        self,
    ):
        question = (
            "求曲线 {x = sin(t), y = cos(2*t)} 在当 t = pi/4 "
            "处的切线方程和法线方程。"
        )
        manual = self.chat(
            question,
            session="p0-manual-ocr-baseline",
            source="text",
        ).get_json()
        ocr_confirmation = self.chat(
            question,
            session="p0-ocr-confirmation-path",
            source="ocr",
        ).get_json()
        confirmed = self.chat(
            "确认",
            session="p0-ocr-confirmation-path",
            source="ocr",
        ).get_json()

        self.assertEqual("ocr_confirm", ocr_confirmation["intent"])
        self.assertEqual(question, ocr_confirmation["formula_text"])
        self.assertNotIn("。。", ocr_confirmation["reply"])
        self.assertEqual("ok", manual["status"])
        self.assertEqual("ok", confirmed["status"])
        self.assertEqual(manual["calculation"], confirmed["calculation"])
        self.assertEqual(manual["reply"], confirmed["reply"])
        self.assertEqual(manual["verification"], confirmed["verification"])
        self.assertEqual(
            manual["knowledge_points"],
            confirmed["knowledge_points"],
        )

    def test_demo_chat_calculates_limit(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "lim x→0 sin(x)/x"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("limit", payload["intent"])
        self.assertEqual("1", payload["calculation"]["limit"])
        self.assertIn(r"\lim_{x\to 0}", payload["formula_latex"])

    def test_demo_chat_calculates_one_sided_limit(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "求 x趋近于0时 1/x 的右极限"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("limit", payload["intent"])
        self.assertEqual("1/x", payload["calculation"]["expression"])
        self.assertEqual("+", payload["calculation"]["direction"])
        self.assertEqual("oo", payload["calculation"]["limit"])

    def test_demo_chat_requests_missing_information(self):
        with patch.object(demo_chat, "GENERAL_CHAT_API_KEY", ""):
            response = self.client.post(
                "/demo/api/chat",
                json={"message": "今天天气怎么样"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("needs_input", payload["status"])
        self.assertEqual("unknown", payload["intent"])
        self.assertIsNone(payload["calculation"])

    def test_demo_chat_answers_general_question_when_configured(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {"message": {"content": "这是普通问答的回答。"}}
                        ]
                    },
                    ensure_ascii=False,
                ).encode("utf-8")

        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
            patch.object(demo_chat, "urlopen", return_value=FakeResponse()),
        ):
            response = self.chat("帮我制定一份复习计划")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertEqual("general", payload["intent"])
        self.assertEqual("这是普通问答的回答。", payload["reply"])
        self.assertIsNone(payload["calculation"])
        self.assertEqual("qa", payload["mode"])

    def test_demo_chat_accepts_teaching_mode(self):
        response = self.chat("求导 x^2", mode="teach")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("teach", payload["mode"])
        self.assertEqual("teaching_step", payload["intent"])
        self.assertIsNone(payload["calculation"])
        self.assertEqual(1, payload["teaching"]["current"])
        self.assertEqual(1, payload["teaching"]["total"])
        self.assertTrue(payload["teaching"]["active"])
        self.assertNotIn("2*x", response.get_data(as_text=True))
        self.assertNotIn("steps", payload["teaching"])

    def test_demo_teaching_parametric_tangent_normal_starts_with_seven_steps(self):
        question = (
            "求曲线 {x = sin(t), y = cos(2*t)} 在当 t = pi/4 "
            "处的切线方程和法线方程。"
        )

        response = self.chat(question, mode="teach")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertEqual("teaching_step", payload["intent"])
        self.assertIsNone(payload["calculation"])
        self.assertEqual(1, payload["teaching"]["current"])
        self.assertEqual(7, payload["teaching"]["total"])
        self.assertEqual("先求 dx/dt", payload["teaching"]["step_title"])
        self.assertIn("dx/dt", payload["teaching"]["prompt"])
        self.assertNotIn("-2*sqrt(2)", response.get_data(as_text=True))
        self.assertNotIn("knowledge_points", payload)

    def test_demo_teaching_parametric_tangent_normal_completes_all_steps(self):
        session = "teaching-parametric-tangent-normal"
        question = (
            "求曲线 {x = sin(t), y = cos(2*t)} 在当 t = pi/4 "
            "处的切线方程和法线方程。"
        )
        answers = (
            "cos(t)",
            "-2*sin(2*t)",
            "(sqrt(2)/2, 0)",
            "-2*sqrt(2)",
            "sqrt(2)/4",
            "y = -2*sqrt(2)*x + 2",
            "y = sqrt(2)*x/4 - 1/4",
        )

        started = self.chat(question, session=session, mode="teach")
        self.assertEqual(200, started.status_code)
        self.assertEqual(1, started.get_json()["teaching"]["current"])

        payload = {}
        for index, answer in enumerate(answers, start=1):
            response = self.chat(
                answer,
                session=session,
                mode="teach",
                teaching_action="answer",
            )
            self.assertEqual(200, response.status_code)
            payload = response.get_json()
            self.assertEqual("correct", payload["teaching"]["feedback_state"])
            if index < len(answers):
                self.assertEqual("teaching_step", payload["intent"])
                self.assertEqual(index + 1, payload["teaching"]["current"])
                self.assertIsNone(payload["calculation"])

        self.assertEqual("solve", payload["intent"])
        self.assertEqual("complete", payload["teaching"]["phase"])
        self.assertFalse(payload["teaching"]["active"])
        self.assertEqual(
            "parametric_tangent_normal",
            payload["calculation"]["topic"],
        )
        self.assertIn("(sqrt(2)/2, 0)", payload["calculation"]["result"])
        self.assertEqual(4, len(payload["knowledge_points"]))
        self.assertEqual(
            "参数方程求导",
            payload["knowledge_points"][0]["title"],
        )

    def test_demo_teaching_accepts_reordered_equivalent_equations(self):
        session = "teaching-reordered-equations"
        question = (
            "求曲线 {x = sin(t), y = cos(2*t)} 在当 t = pi/4 "
            "处的切线方程和法线方程。"
        )

        self.chat(question, session=session, mode="teach")
        for answer in (
            "cos(t)",
            "-2*sin(2*t)",
            "(sqrt(2)/2, 0)",
            "-2*sqrt(2)",
            "sqrt(2)/4",
        ):
            response = self.chat(
                answer,
                session=session,
                mode="teach",
                teaching_action="answer",
            )
            self.assertEqual("correct", response.get_json()["teaching"]["feedback_state"])

        wrong_tangent = self.chat(
            "y = -2*sqrt(2)*x + 3",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()
        self.assertEqual("wrong", wrong_tangent["teaching"]["feedback_state"])
        self.assertEqual(6, wrong_tangent["teaching"]["current"])

        reordered_tangent = self.chat(
            "2√2x + y - 2 = 0",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()
        self.assertEqual("correct", reordered_tangent["teaching"]["feedback_state"])
        self.assertEqual(7, reordered_tangent["teaching"]["current"])

        reordered_normal = self.chat(
            "4y = √2x - 1",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()
        self.assertEqual("correct", reordered_normal["teaching"]["feedback_state"])
        self.assertEqual("complete", reordered_normal["teaching"]["phase"])

    def test_demo_teaching_stops_when_auto_solve_fails(self):
        def failed_solve(message, history=None, mode="qa"):
            return {
                "status": "error",
                "intent": "solve",
                "reply": "自动求解暂时没有完成。",
                "formula_latex": "",
                "formula_text": "",
                "calculation": None,
            }

        with patch.object(
            wsgi_app,
            "build_chat_response",
            side_effect=failed_solve,
        ):
            response = self.chat(
                "求参数方程切线",
                session="teaching-solve-failure",
                mode="teach",
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("error", payload["status"])
        self.assertEqual("teaching_failed", payload["intent"])
        self.assertIsNone(payload["calculation"])
        self.assertNotIn("teaching", payload)
        self.assertNotIn("knowledge_points", payload)
        self.assertIn("系统已停止后续教学步骤和知识点生成", payload["reply"])

    def test_demo_teaching_stops_when_calculation_payload_is_missing(self):
        def incomplete_solve(message, history=None, mode="qa"):
            return {
                "status": "ok",
                "intent": "solve",
                "reply": "求解完成。",
                "formula_latex": "",
                "formula_text": "",
                "calculation": None,
            }

        with patch.object(
            wsgi_app,
            "build_chat_response",
            side_effect=incomplete_solve,
        ):
            response = self.chat(
                "求参数方程切线",
                session="teaching-calculation-missing",
                mode="teach",
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("error", payload["status"])
        self.assertEqual("teaching_failed", payload["intent"])
        self.assertIsNone(payload["calculation"])
        self.assertNotIn("teaching", payload)
        self.assertNotIn("knowledge_points", payload)

    def test_demo_teaching_wrong_answer_hints_without_revealing(self):
        session = "teaching-wrong"
        started = self.chat("求导 x^2", session=session, mode="teach")

        wrong = self.chat(
            "3*x",
            session=session,
            mode="teach",
            teaching_action="answer",
        )

        self.assertEqual(200, wrong.status_code)
        payload = wrong.get_json()
        self.assertEqual("teaching_step", payload["intent"])
        self.assertEqual(1, payload["teaching"]["current"])
        self.assertEqual(1, payload["teaching"]["attempts"])
        self.assertEqual("wrong", payload["teaching"]["feedback_state"])
        self.assertTrue(payload["teaching"]["hint"])
        self.assertNotIn("2*x", wrong.get_data(as_text=True))
        self.assertIsNone(payload["calculation"])
        self.assertTrue(started.get_json()["teaching"]["active"])

    def test_demo_teaching_correct_answer_completes_and_reveals_solution(self):
        session = "teaching-correct"
        self.chat("求导 x^2", session=session, mode="teach")

        completed = self.chat(
            "2x",
            session=session,
            mode="teach",
            teaching_action="answer",
        )

        self.assertEqual(200, completed.status_code)
        payload = completed.get_json()
        self.assertEqual("verify", payload["intent"])
        self.assertEqual("complete", payload["teaching"]["phase"])
        self.assertFalse(payload["teaching"]["active"])
        self.assertTrue(payload["teaching"]["can_restart"])
        self.assertEqual("2*x", payload["calculation"]["derivative"])
        self.assertIn("**详细计算步骤**", payload["reply"])
        self.assertIn("**最终答案**", payload["reply"])

    def test_demo_teaching_supports_hint_explain_skip_and_restart(self):
        session = "teaching-actions"
        self.chat("积分 0 到 1 x^2", session=session, mode="teach")

        hinted = self.chat(
            "hint",
            session=session,
            mode="teach",
            teaching_action="hint",
        ).get_json()
        explained = self.chat(
            "explain",
            session=session,
            mode="teach",
            teaching_action="explain",
        ).get_json()
        skipped = self.chat(
            "skip",
            session=session,
            mode="teach",
            teaching_action="skip",
        ).get_json()
        restarted = self.chat(
            "restart",
            session=session,
            mode="teach",
            teaching_action="restart",
        ).get_json()

        self.assertTrue(hinted["teaching"]["hint"])
        self.assertTrue(explained["teaching"]["explanation"])
        self.assertEqual(2, skipped["teaching"]["current"])
        self.assertEqual(1, restarted["teaching"]["current"])
        self.assertEqual(0, restarted["teaching"]["attempts"])
        self.assertIsNone(restarted["calculation"])

    def test_demo_teaching_existing_limit_rejects_nonexistent_answer(self):
        session = "teaching-limit-exists"
        started = self.chat(
            "lim x→0 sin(x)/x",
            session=session,
            mode="teach",
        ).get_json()

        self.assertEqual("先求左极限", started["teaching"]["step_title"])
        self.assertEqual(3, started["teaching"]["total"])

        left = self.chat(
            "极限是1",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()
        right = self.chat(
            "1",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()
        wrong = self.chat(
            "不存在",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()

        self.assertEqual("correct", left["teaching"]["feedback_state"])
        self.assertEqual("correct", right["teaching"]["feedback_state"])
        self.assertEqual(3, right["teaching"]["current"])
        self.assertEqual(3, wrong["teaching"]["current"])
        self.assertEqual("wrong", wrong["teaching"]["feedback_state"])
        self.assertEqual(1, wrong["teaching"]["attempts"])
        self.assertTrue(wrong["teaching"]["hint"])
        self.assertNotIn("$1$", wrong["teaching"]["hint"])

        completed = self.chat(
            "极限是1",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()

        self.assertEqual("complete", completed["teaching"]["phase"])
        self.assertEqual("limit", completed["intent"])
        self.assertEqual("1", completed["calculation"]["limit"])

    def test_demo_teaching_nonexistent_limit_rejects_numeric_answer(self):
        session = "teaching-limit-missing"
        started = self.chat(
            "lim x→0 1/x",
            session=session,
            mode="teach",
        ).get_json()

        self.assertEqual(3, started["teaching"]["total"])
        self.assertEqual(
            "correct",
            self.chat(
                "-∞",
                session=session,
                mode="teach",
                teaching_action="answer",
            ).get_json()["teaching"]["feedback_state"],
        )
        self.assertEqual(
            "correct",
            self.chat(
                "∞",
                session=session,
                mode="teach",
                teaching_action="answer",
            ).get_json()["teaching"]["feedback_state"],
        )
        wrong = self.chat(
            "0",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()

        self.assertEqual("wrong", wrong["teaching"]["feedback_state"])
        self.assertEqual(3, wrong["teaching"]["current"])

        completed = self.chat(
            "极限不存在",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()

        self.assertEqual("complete", completed["teaching"]["phase"])
        self.assertIs(False, completed["calculation"]["exists"])

    def test_demo_teaching_one_sided_infinite_limit_rejects_nonexistent(self):
        session = "teaching-one-sided-infinite"
        started = self.chat(
            "求 x趋近于0时 1/x 的右极限",
            session=session,
            mode="teach",
        ).get_json()

        self.assertEqual(1, started["teaching"]["total"])
        wrong = self.chat(
            "不存在",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()

        self.assertEqual("wrong", wrong["teaching"]["feedback_state"])
        self.assertEqual(1, wrong["teaching"]["current"])
        self.assertEqual(1, wrong["teaching"]["attempts"])

        completed = self.chat(
            "极限是∞",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()

        self.assertEqual("complete", completed["teaching"]["phase"])
        self.assertEqual("oo", completed["calculation"]["limit"])

    def test_demo_teaching_persists_progress_across_requests(self):
        session = "teaching-progress"
        first = self.chat(
            "积分 0 到 1 x^2",
            session=session,
            mode="teach",
        ).get_json()
        second = self.chat(
            "x^3/3",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()
        completed = self.chat(
            "1/3",
            session=session,
            mode="teach",
            teaching_action="answer",
        ).get_json()

        self.assertEqual(1, first["teaching"]["current"])
        self.assertEqual(2, second["teaching"]["current"])
        self.assertEqual(2, second["teaching"]["total"])
        self.assertIsNone(second["calculation"])
        self.assertEqual("complete", completed["teaching"]["phase"])
        self.assertEqual("1/3", completed["calculation"]["integral"])

    def test_demo_teaching_continue_is_an_answer_not_ocr_confirmation(self):
        session = "teaching-continue"
        self.chat("求导 x^2", session=session, mode="teach")

        response = self.chat(
            "继续",
            session=session,
            mode="teach",
            pending_question="求导 x^2",
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("teaching_step", payload["intent"])
        self.assertEqual("wrong", payload["teaching"]["feedback_state"])
        self.assertEqual(1, payload["teaching"]["attempts"])

    def test_demo_teaching_ocr_confirmation_starts_lesson(self):
        response = self.chat(
            "确认",
            session="teaching-ocr",
            mode="teach",
            source="ocr",
            pending_question="求导 x^2",
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("teaching_step", payload["intent"])
        self.assertEqual(1, payload["teaching"]["current"])
        self.assertIn("x^2", payload["teaching"]["question"])
        self.assertIsNone(payload["calculation"])

    def test_demo_teaching_can_restart_after_completion(self):
        session = "teaching-complete-restart"
        self.chat("求导 x^2", session=session, mode="teach")
        self.chat(
            "2x",
            session=session,
            mode="teach",
            teaching_action="answer",
        )

        response = self.chat(
            "restart",
            session=session,
            mode="teach",
            teaching_action="restart",
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("teaching_step", payload["intent"])
        self.assertTrue(payload["teaching"]["active"])
        self.assertEqual(1, payload["teaching"]["current"])
        self.assertIsNone(payload["calculation"])

    def test_demo_teaching_reset_expires_active_session(self):
        session = "teaching-reset"
        self.chat("求导 x^2", session=session, mode="teach")

        reset = self.client.post(
            "/demo/api/teaching/reset",
            headers={"X-Demo-Session": "test-session-teaching-reset"},
        )
        expired = self.chat(
            "hint",
            session=session,
            mode="teach",
            teaching_action="hint",
        )

        self.assertEqual(200, reset.status_code)
        self.assertEqual("teaching_reset", reset.get_json()["state"])
        self.assertEqual(200, expired.status_code)
        self.assertEqual("teaching_expired", expired.get_json()["intent"])

    def test_demo_teaching_does_not_use_response_cache(self):
        with patch.object(
            wsgi_app,
            "build_chat_response",
            wraps=wsgi_app.build_chat_response,
        ) as build_mock:
            first = self.chat(
                "求导 x^2",
                session="teaching-cache-a",
                mode="teach",
            )
            second = self.chat(
                "求导 x^2",
                session="teaching-cache-b",
                mode="teach",
            )

        self.assertEqual("teaching_step", first.get_json()["intent"])
        self.assertEqual("teaching_step", second.get_json()["intent"])
        self.assertNotIn("cached", first.get_json())
        self.assertNotIn("cached", second.get_json())
        self.assertEqual(2, build_mock.call_count)

    def test_demo_chat_rejects_unknown_mode(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "求导 x^2", "mode": "other"},
        )

        self.assertEqual(422, response.status_code)

    def test_demo_chat_keeps_math_questions_out_of_general_chat(self):
        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
            patch.object(demo_chat, "urlopen") as mocked_urlopen,
        ):
            response = self.chat("求导 x^2")

        self.assertEqual("verify", response.get_json()["intent"])
        mocked_urlopen.assert_not_called()

    def test_demo_chat_distinguishes_http_failures(self):
        cases = (
            (401, "鉴权失败"),
            (403, "免费额度"),
            (429, "请求过于频繁"),
            (503, "临时错误"),
        )

        for status_code, expected_message in cases:
            with self.subTest(status_code=status_code):
                error = HTTPError(
                    "https://chat.test/chat",
                    status_code,
                    "chat failure",
                    {},
                    None,
                )
                with (
                    patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
                    patch.object(
                        demo_chat,
                        "GENERAL_CHAT_API_URL",
                        "https://chat.test/chat",
                    ),
                    patch.object(demo_chat, "urlopen", side_effect=error),
                ):
                    payload = demo_chat._build_general_chat_response(
                        "帮我制定一份复习计划",
                        None,
                    )

                self.assertEqual("error", payload["status"])
                self.assertIn(expected_message, payload["reply"])
                self.assertIn("高数计算仍可继续使用", payload["reply"])

    def test_demo_chat_reuses_the_previous_question(self):
        response = self.client.post(
            "/demo/api/chat",
            json={
                "message": "再算一遍上一题",
                "history": [
                    {"role": "user", "text": "求导 x^2"},
                    {"role": "assistant", "text": "导数是 2*x。"},
                ],
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("verify", payload["intent"])
        self.assertEqual("2*x", payload["calculation"]["derivative"])
        self.assertIn("x^2", payload["history_used"])

    def test_demo_chat_lists_recent_questions(self):
        response = self.client.post(
            "/demo/api/chat",
            json={
                "message": "我以前做过哪些题",
                "history": [
                    {"role": "user", "text": "求导 x^2"},
                    {"role": "user", "text": "积分 0 到 1 x^2"},
                ],
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("history", payload["intent"])
        self.assertEqual(2, len(payload["history_questions"]))

    def test_demo_page_sends_limited_history_and_caches_repeated_questions(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("MAX_REQUEST_HISTORY = 20", html)
        self.assertIn("history,", html)
        self.assertIn("source,", html)
        self.assertIn(
            'item) => item.state === "success" && !usableRecognizedText(item),',
            html,
        )
        self.assertIn(
            'addRequest(text, "ocr", true, `image:${item.id}`);',
            html,
        )
        self.assertIn(
            'const source = options.source === "ocr" ? "ocr" : "text";',
            html,
        )
        self.assertIn(
            "const useComposerAsSingleOcr = insertedItems.length === 1;",
            html,
        )
        self.assertIn(
            "if (insertedText && !unchangedInsertion) {",
            html,
        )
        self.assertIn("responseCache", html)
        self.assertIn("includes(data.intent)", html)
        self.assertIn("REQUEST_TIMEOUT_MS = 45000", html)
        self.assertIn("X-Demo-Session", html)
        self.assertIn('id="composerMode"', html)
        self.assertIn('aria-disabled="false"', html)
        self.assertIn('data-composer-mode="qa"', html)
        self.assertIn('data-composer-mode="teach"', html)
        self.assertIn('aria-label="回答方式"', html)
        self.assertIn("if (requestInFlight && persist)", html)
        self.assertIn("button.disabled = active;", html)
        self.assertIn(
            'composerModeControl.setAttribute(\n          "aria-disabled",\n          String(active),\n        );',
            html,
        )
        self.assertIn(
            "window.localStorage.getItem(COMPOSER_MODE_KEY)",
            html,
        )
        self.assertIn(
            "function responseCacheKey(question, mode = composerMode)",
            html,
        )
        self.assertIn("const requestMode = composerMode;", html)
        self.assertIn("mode: requestMode,", html)
        self.assertIn(
            'stepTitle: String(value.step_title || value.stepTitle || ""),',
            html,
        )
        self.assertIn(
            "canSkip: Boolean(value.can_skip ?? value.canSkip),",
            html,
        )
        self.assertIn(
            "canRestart: Boolean(value.can_restart ?? value.canRestart),",
            html,
        )
        self.assertIn(
            'value.feedback_state ?? value.feedbackState ?? ""',
            html,
        )
        self.assertIn("function parseSolutionSections(rawText)", html)
        self.assertIn("const SOLUTION_SECTION_TITLES", html)
        self.assertNotIn(".split(/(?<=[。！？；])(?=\\S)/u)", html)

    def test_demo_page_handles_mobile_viewport_and_ocr_timeout(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("interactive-widget=resizes-content", html)
        self.assertIn("padding-left: env(safe-area-inset-left)", html)
        self.assertIn("padding-right: env(safe-area-inset-right)", html)
        self.assertIn("height: var(--app-height, 100dvh)", html)
        self.assertIn("max-height: min(292px, 42dvh)", html)
        self.assertIn("OCR_REQUEST_TIMEOUT_MS = 90000", html)
        self.assertIn("function syncAppViewportHeight()", html)
        self.assertIn(
            'window.visualViewport.addEventListener("resize", syncAppViewportHeight)',
            html,
        )
        self.assertIn(
            '"图片识别超时，请检查网络后重试，或改用文字输入。"',
            html,
        )
        self.assertIn("window.clearTimeout(ocrTimeoutId)", html)

    def test_demo_page_reports_slow_request_progress(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("SLOW_REQUEST_NOTICE_MS = 8000", html)
        self.assertIn("VERY_SLOW_REQUEST_NOTICE_MS = 22000", html)
        self.assertIn("function updateLoadingDetail(loadingId, detail)", html)
        self.assertIn('"网络较慢，仍在处理，请稍候。"', html)
        self.assertIn(
            '"仍在等待计算服务，最长大约 45 秒；完成前请不要重复发送。"',
            html,
        )
        self.assertIn("const slowNoticeId = window.setTimeout(", html)
        self.assertIn("const verySlowNoticeId = window.setTimeout(", html)
        self.assertIn("window.clearTimeout(slowNoticeId)", html)
        self.assertIn("window.clearTimeout(verySlowNoticeId)", html)

    def test_demo_chat_solves_basic_arithmetic(self):
        cases = (
            ("1+1", "2"),
            ("12-7", "5"),
            ("6×7", "42"),
            ("8÷2", "4"),
            ("(1+2)*3", "9"),
            ("3.5+1.2", "4.7"),
            ("1/2+1/3", "5/6"),
            ("2^10", "1024"),
        )

        for message, expected in cases:
            with self.subTest(message=message):
                response = self.chat(message)

                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertEqual("arithmetic", payload["intent"])
                self.assertEqual(expected, payload["calculation"]["result"])

    def test_demo_chat_reports_division_by_zero(self):
        response = self.chat("1/0")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("arithmetic", payload["intent"])
        self.assertEqual("error", payload["status"])
        self.assertIn("除数不能为 0", payload["reply"])

    def test_demo_chat_caches_repeated_questions_per_session(self):
        first = self.chat("求导 x^2", session="shared")
        second = self.chat("求导 x^2", session="shared")
        other_session = self.chat("求导 x^2", session="other")

        self.assertEqual(200, first.status_code)
        self.assertIsNot(True, first.get_json().get("cached"))
        self.assertIs(True, second.get_json()["cached"])
        self.assertIsNot(True, other_session.get_json().get("cached"))

    def test_demo_chat_cache_is_isolated_by_mode(self):
        def fake_build(message, history, mode):
            return {
                "status": "ok",
                "intent": "verify",
                "reply": f"{mode}:{message}",
                "formula_latex": "",
                "formula_text": "",
                "calculation": {
                    "expression": "x^2",
                    "variable": "x",
                    "derivative": "2*x",
                    "derivative_function": "2*x",
                },
                "verified": True,
                "verification": {
                    "passed": True,
                    "kind": "derivative",
                    "checks": [
                        {
                            "name": "derivative_contract",
                            "passed": True,
                        }
                    ],
                },
            }

        with patch.object(
            wsgi_app,
            "build_chat_response",
            side_effect=fake_build,
        ) as build_mock:
            qa = self.chat("同一道题", session="mode-cache", mode="qa")
            teach = self.chat("同一道题", session="mode-cache", mode="teach")

        self.assertEqual(200, qa.status_code)
        self.assertEqual(200, teach.status_code)
        self.assertTrue(qa.get_json()["reply"].startswith("qa:"))
        teaching_payload = teach.get_json()
        self.assertEqual("teach", teaching_payload["mode"])
        self.assertEqual("teaching_step", teaching_payload["intent"])
        self.assertIsNone(teaching_payload["calculation"])
        self.assertNotIn("cached", teaching_payload)
        self.assertEqual(2, build_mock.call_count)

    def test_demo_chat_does_not_cache_history_answers(self):
        first = self.chat("我以前做过哪些题", session="history")
        second = self.chat("我以前做过哪些题", session="history")

        self.assertEqual("history", first.get_json()["intent"])
        self.assertIsNot(True, second.get_json().get("cached"))

    def test_demo_chat_varies_greeting_answers_without_caching_them(self):
        first = self.chat("你好", session="greeting")
        second = self.chat("你好", session="greeting")

        self.assertEqual("help", first.get_json()["intent"])
        self.assertIsNot(True, second.get_json().get("cached"))
        self.assertIn(second.get_json()["reply"], demo_chat._HELP_REPLIES)

    def test_demo_page_welcome_copy_does_not_repeat_greeting_replies(self):
        html = self.client.get("/demo").get_data(as_text=True)

        for reply in demo_chat._HELP_REPLIES:
            self.assertNotIn(reply, html)

    def test_demo_chat_does_not_repeat_a_history_followup(self):
        response = self.chat(
            "再算一遍上一题",
            history=[
                {"role": "user", "text": "继续"},
                {"role": "user", "text": "求导 x^2"},
                {"role": "user", "text": "再算一遍上一题"},
            ],
            session="followup",
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("verify", payload["intent"])
        self.assertEqual("2*x", payload["calculation"]["derivative"])
        self.assertEqual("求导 x^2", payload["history_used"])

    def test_demo_remains_public_when_api_key_is_enabled(self):
        with patch.object(wsgi_app, "API_KEY", "test-secret"):
            page = self.client.get("/demo")
            demo_api = self.client.post(
                "/demo/api/verify",
                json={"expression": "x^2", "variable": "x"},
            )
            chat_api = self.client.post(
                "/demo/api/chat",
                json={"message": "求导 x^2"},
            )
            protected_api = self.client.post(
                "/verify",
                json={"expression": "x^2", "variable": "x"},
            )
            public_plot = self.client.get(
                "/plot.svg",
                query_string={
                    "expression": "sin(x)",
                    "variable": "x",
                    "x_min": "-3",
                    "x_max": "3",
                    "samples": 80,
                    "width": 320,
                    "height": 240,
                },
            )
            protected_plot = self.client.post(
                "/plot-query",
                query_string={
                    "expression": "sin(x)",
                    "variable": "x",
                },
            )

        self.assertEqual(200, page.status_code)
        self.assertEqual(200, demo_api.status_code)
        self.assertEqual(200, chat_api.status_code)
        self.assertEqual(401, protected_api.status_code)
        self.assertEqual(200, public_plot.status_code)
        self.assertTrue(
            public_plot.content_type.startswith("image/svg+xml")
        )
        self.assertEqual(401, protected_plot.status_code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
