"""middleware/permissions.py 단위 테스트.

정본: docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-18_06_미들웨어_전체_설계_정리.md §3~7

`build_filesystem_permissions()`가 만든 규칙이 실제 `deepagents`의
`_check_fs_permission()`(순서대로 첫 매치 반환 — 스코프가 아니라 리스트 순서가
이긴다)을 통과했을 때 의도한 판정이 나오는지, 그리고 이 규칙이 실제
`FilesystemMiddleware` 생성자를 통과한 뒤에도 살아있는지(치환 과정에서 조용히
사라지지 않는지)를 확인한다.
"""

from django.test import SimpleTestCase

from services.agent_runtime.middleware.permissions import build_filesystem_permissions


class BuildFilesystemPermissionsTests(SimpleTestCase):
    def test_current_project_write_is_allowed(self):
        from deepagents.middleware.filesystem import _check_fs_permission

        rules = build_filesystem_permissions(project_id="PJ001")

        self.assertEqual(
            _check_fs_permission(rules, "write", "/memories/projects/PJ001.md"), "allow"
        )

    def test_other_project_read_is_denied(self):
        from deepagents.middleware.filesystem import _check_fs_permission

        rules = build_filesystem_permissions(project_id="PJ001")

        self.assertEqual(
            _check_fs_permission(rules, "read", "/memories/projects/PJ002.md"), "deny"
        )

    def test_shared_agents_md_is_unaffected(self):
        """§3~7 — 이 규칙은 `/memories/projects/**`에만 걸리고, `/memories/AGENTS.md`
        (팀 공유) `/memories/users/preferences.md`(개인)는 건드리지 않는다."""
        from deepagents.middleware.filesystem import _check_fs_permission

        rules = build_filesystem_permissions(project_id="PJ001")

        self.assertEqual(_check_fs_permission(rules, "write", "/memories/AGENTS.md"), "allow")
        self.assertEqual(
            _check_fs_permission(rules, "write", "/memories/users/preferences.md"), "allow"
        )

    def test_no_project_id_denies_all_project_memory(self):
        """프로젝트 문맥 없이 시작한 세션(project_id=None) — 애매하면 차단한다
        (fail-closed)."""
        from deepagents.middleware.filesystem import _check_fs_permission

        rules = build_filesystem_permissions(project_id=None)

        self.assertEqual(
            _check_fs_permission(rules, "read", "/memories/projects/PJ001.md"), "deny"
        )

    def test_unsafe_project_id_falls_back_to_deny_all(self):
        """§4 — glob 메타문자나 경로 구분자가 섞인 project_id는 원래 있어선 안 되는
        값으로 보고 project_id=None과 동일하게 취급한다(allow 규칙을 안 만든다)."""
        from deepagents.middleware.filesystem import _check_fs_permission

        rules = build_filesystem_permissions(project_id="PJ*/../001")

        self.assertEqual(
            _check_fs_permission(rules, "read", "/memories/projects/PJ001.md"), "deny"
        )
        # allow 규칙이 아예 안 만들어졌는지도 직접 확인 — deny 규칙 하나만 있어야 한다.
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].mode, "deny")

    def test_rule_order_puts_allow_before_deny(self):
        """`_check_fs_permission`은 리스트 순서대로 첫 매치를 반환한다 — allow가
        deny보다 뒤에 있으면 항상 deny가 먼저 이겨 이 기능 전체가 무의미해진다."""
        rules = build_filesystem_permissions(project_id="PJ001")

        self.assertEqual(rules[0].mode, "allow")
        self.assertEqual(rules[-1].mode, "deny")


class FilesystemMiddlewareIntegrationTests(SimpleTestCase):
    """실제 `build_memory_backend()` + `build_filesystem_permissions()` +
    `FilesystemMiddleware(**fs_kwargs)` 조합이 예외 없이 만들어지고, `_permissions`가
    치환 과정에서 사라지지 않는지 확인한다(Mock이 아니라 실제 객체 조합 —
    `test_memory_backend.py`의 `test_survives_actual_format_agent_memory_call`과
    같은 사고방식: 생성자 검사만으로는 못 잡는 통합 버그가 있을 수 있어서)."""

    def test_real_filesystem_middleware_keeps_permissions_after_construction(self):
        from deepagents.middleware.filesystem import FilesystemMiddleware

        from services.agent_runtime.memory.backend import build_memory_backend

        backend = build_memory_backend(team_id="TM001", agent_id="AG001", account_id="AC001")
        rules = build_filesystem_permissions(project_id="PJ001")

        middleware = FilesystemMiddleware(backend=backend, tools=["read_file"], _permissions=rules)

        self.assertEqual(middleware._permissions, rules)

    def test_real_filesystem_middleware_without_permissions_defaults_to_empty(self):
        """빈 시퀀스면(project_id 없을 때도 실제로는 deny 규칙 하나가 생기므로
        해당 안 됨 — 이 테스트는 `permissions=` 자체를 아예 안 넘겼을 때, 즉
        memory_provider가 없어 §7 경로 자체가 안 도는 경우와 동일한 기본 동작을
        확인한다)."""
        from deepagents.middleware.filesystem import FilesystemMiddleware

        middleware = FilesystemMiddleware(tools=["read_file"])

        self.assertEqual(middleware._permissions, [])
