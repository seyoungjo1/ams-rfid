package com.ams.rfid.core

/**
 * 필라멘트 DB 업데이트 판단 로직. 네트워크/안드로이드와 무관한 순수 함수만 둔다.
 */
object LibraryUpdate {
    /** 앱이 이해하는 index.json/manifest.json 형식 버전 (build_tag_library.py 의 FORMAT_VERSION). */
    const val SUPPORTED_FORMAT = 1

    data class Diff(val added: List<String>, val removed: List<String>)

    /** 색상 키("분류/재질/색상") 목록을 비교해 추가/삭제된 항목을 돌려준다. */
    fun diff(current: Collection<String>, incoming: Collection<String>): Diff {
        val currentSet = current.toSet()
        val incomingSet = incoming.toSet()
        return Diff(
            added = incoming.filter { it !in currentSet },
            removed = current.filter { it !in incomingSet },
        )
    }

    /**
     * 원격 DB를 사용자에게 제안할지 판단한다.
     * 형식이 호환되고, 기준 커밋이 다르며, 현재 DB보다 나중에 만들어진 경우에만 제안한다.
     * (생성 시각은 ISO-8601 UTC 문자열이라 문자열 비교로 순서가 맞다.)
     */
    fun isNewer(
        currentCommit: String,
        currentGenerated: String,
        remoteCommit: String,
        remoteGenerated: String,
        remoteFormat: Int,
    ): Boolean = remoteFormat == SUPPORTED_FORMAT &&
        remoteCommit.isNotEmpty() &&
        remoteCommit != currentCommit &&
        remoteGenerated > currentGenerated

    private val GENERATED = Regex("\"generated\"\\s*:\\s*\"([^\"]+)\"")

    /** index.json 앞부분만 보고 생성 시각을 읽는다(전체 파싱 없이 내장/내려받은 DB 중 최신 선택). */
    fun peekGenerated(head: String): String? = GENERATED.find(head)?.groupValues?.get(1)

    /** "분류/재질/색상" → "재질 · 색상" */
    fun displayName(key: String): String {
        val parts = key.split('/')
        return if (parts.size >= 3) "${parts[parts.size - 2]} · ${parts.last()}" else key
    }
}
