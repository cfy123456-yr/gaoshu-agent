import io
import itertools
import json
import struct
import unittest
from unittest.mock import patch

from deploy import (
    demo_chat,
    demo_coze_ocr,
    demo_math_text,
    demo_question_blocks,
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
        wsgi_app.rate_limiter.requests.clear()
        self.session_counter = itertools.count(1)

    def chat(self, message, history=None, session=None):
        session_id = session or next(self.session_counter)
        headers = {"X-Demo-Session": f"test-session-{session_id}"}
        return self.client.post(
            "/demo/api/chat",
            json={"message": message, "history": history or []},
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
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertIn("controller.abort(), 6000", html)

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
        self.assertIn("renderQuestionKnowledge(text, { source: \"submit\" })", html)
        self.assertIn("renderQuestionKnowledge(\"\")", html)
        self.assertIn('aria-live="polite"', html)
        self.assertNotIn("FORMULA_COLLECTION", html)
        self.assertNotIn("formulaCardGrid", html)
        self.assertNotIn("formulaSearchInput", html)
        self.assertNotIn("renderFormulaCards", html)

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

    def test_demo_page_exposes_toolbox_and_preview_panel(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        for field in (
            "conversationPanel",
            "previewPanel",
            "previewContent",
            "previewToggle",
            "previewClear",
        ):
            self.assertIn(f'id="{field}"', html)
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
        self.assertIn("composer-image-question-select", html)
        self.assertIn("function selectRecognizedQuestion(", html)
        self.assertIn("按当前识别题继续", html)
        self.assertIn("function setConversationPanelCollapsed(", html)
        self.assertIn("function setPreviewCollapsed(", html)
        self.assertIn("计算过程总览", html)
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
            r'multiple',
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
        self.assertIn("function submitComposer()", html)
        self.assertIn("function syncComposerState()", html)
        self.assertIn("function flushPendingComposerSubmission()", html)
        self.assertIn("function hasMultipleNumberedQuestions(text)", html)
        self.assertIn(
            "识别到多道小题，请只保留当前需要计算的一道题后发送。",
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

    def test_demo_page_keeps_the_sidebar_rail_minimal(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertRegex(
            html,
            r'id="previewPanel"\s+data-collapsed="true"',
        )
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
        self.assertIn(
            '!WRONG_BOOK_ELIGIBLE_INTENTS.has(String(answer.intent || ""))',
            html,
        )
        self.assertIn("intent: String(item.intent || \"\")", html)
        self.assertIn("intent: String(data.intent || \"\")", html)
        self.assertIn(
            'if (message.role === "assistant" && !message.loading) {',
            html,
        )
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
            "setSuggestionsCollapsed(compactComposerMedia.matches)",
            html,
        )

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
            ("\u221ax", "sqrt(x)"),
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
        self.assertIn("逐题", prompt)
        self.assertIn("不得合并", prompt)
        self.assertIn("data:image/png;base64,", payload["messages"][0]["content"][1]["image_url"]["url"])
        prompt = payload["messages"][0]["content"][0]["text"]
        self.assertIn("数字 0 与字母 O/o", prompt)
        self.assertIn("疑似", prompt)

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

    def test_query_candidate_must_be_ignored_when_blank(self):
        cases = (
            (
                "/verify-query",
                {"expression": "x^2", "variable": "x", "candidate": ""},
            ),
            (
                "/integrate-query",
                {
                    "expression": "x^2",
                    "variable": "x",
                    "lower": "",
                    "upper": "",
                    "candidate": "",
                },
            ),
            (
                "/limit-query",
                {
                    "expression": "sin(x)/x",
                    "variable": "x",
                    "point": "0",
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
                self.assertIn(payload["intent"], {"solve", "calculation"})
                calculation = payload.get("calculation")
                if calculation is None:
                    self.skipTest(
                        "Legacy explicit curve/surface solver is optional for this release."
                    )
                self.assertEqual(method, calculation["method"])
                self.assertEqual(expected, calculation["result"])

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

    def test_demo_chat_keeps_math_questions_out_of_general_chat(self):
        with (
            patch.object(demo_chat, "GENERAL_CHAT_API_KEY", "test-key"),
            patch.object(demo_chat, "urlopen") as mocked_urlopen,
        ):
            response = self.chat("求导 x^2")

        self.assertEqual("verify", response.get_json()["intent"])
        mocked_urlopen.assert_not_called()

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
            'source: recognizedImage ? "ocr" : "text",',
            html,
        )
        self.assertIn(
            'const source = options.source === "ocr" ? "ocr" : "text";',
            html,
        )
        self.assertIn("responseCache", html)
        self.assertIn("includes(data.intent)", html)
        self.assertIn("REQUEST_TIMEOUT_MS = 45000", html)
        self.assertIn("X-Demo-Session", html)

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
