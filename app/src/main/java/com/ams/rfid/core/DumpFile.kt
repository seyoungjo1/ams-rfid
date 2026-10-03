package com.ams.rfid.core

/**
 * 외부 덤프 파일을 [TagDump] 으로 읽어들인다. FM11RF08S(= MIFARE Classic 1K 호환) 칩에서
 * 뜬 덤프를 빈 카드에 그대로 굽기 위한 입력 파서다. 다음 형식을 받는다:
 *
 *  - 원시 바이너리(.bin/.dump): 1024바이트(64블록). Proxmark fm11rf08s 복구 결과처럼
 *    1152바이트(72블록)로 키 정보가 뒤에 붙은 파일은 앞의 1024바이트만 쓴다.
 *  - Proxmark JSON(.json): { "blocks": { "0": "<hex>", ... } }
 *  - Flipper NFC(.nfc): "Block NN: XX XX ..." 줄들
 *
 * 안드로이드/네트워크와 무관한 순수 로직이라 JVM 단위 테스트가 가능하다.
 */
object DumpFile {
    sealed class Result {
        data class Ok(val dump: TagDump, val format: String) : Result()
        data class Error(val message: String) : Result()
    }

    private val JSON_BLOCK = Regex("\"(\\d{1,3})\"\\s*:\\s*\"([0-9A-Fa-f?]{32})\"")
    private val FLIPPER_BLOCK = Regex("(?im)^Block\\s+(\\d{1,3})\\s*:\\s*([0-9A-Fa-f? ]+)$")

    fun parse(bytes: ByteArray): Result {
        val text = decodeTextOrNull(bytes)

        if (text != null) {
            val trimmed = text.trimStart()
            if (trimmed.startsWith("Filetype: Flipper", ignoreCase = true) || FLIPPER_BLOCK.containsMatchIn(text)) {
                blocksFrom(FLIPPER_BLOCK, text)?.let { return Result.Ok(it, "Flipper NFC") }
            }
            if (trimmed.startsWith("{")) {
                blocksFrom(JSON_BLOCK, text)?.let { return Result.Ok(it, "JSON") }
                return Result.Error("JSON 덤프에서 blocks 를 찾지 못했습니다")
            }
        }

        // 원시 바이너리
        return when {
            bytes.size >= TagDump.SIZE -> Result.Ok(TagDump.of(bytes), binLabel(bytes.size))
            else -> Result.Error("MIFARE 1K 덤프가 아닙니다 (${bytes.size}바이트, 1024바이트 필요)")
        }
    }

    private fun binLabel(size: Int): String = when (size) {
        TagDump.SIZE -> "BIN 1K"
        1152 -> "BIN (fm11rf08s 72블록)"
        else -> "BIN ${size}B"
    }

    /** 블록 번호 → hex 를 모아 64블록 덤프를 만든다. '?' 는 00 으로 채운다. */
    private fun blocksFrom(regex: Regex, text: String): TagDump? {
        val blocks = arrayOfNulls<ByteArray>(TagDump.BLOCKS)
        var found = 0
        for (m in regex.findAll(text)) {
            val index = m.groupValues[1].toIntOrNull() ?: continue
            if (index !in 0 until TagDump.BLOCKS) continue
            val hex = m.groupValues[2].replace(" ", "").replace("?", "0")
            if (hex.length != 32) continue
            blocks[index] = runCatching { hex.hexToBytes() }.getOrNull() ?: continue
            found++
        }
        if (found == 0 || blocks[0] == null) return null
        return TagDump.fromBlocks(blocks.toList())
    }

    /** 유효한 UTF-8/ASCII 텍스트처럼 보이면 문자열로, 아니면 null(= 바이너리). */
    private fun decodeTextOrNull(bytes: ByteArray): String? {
        val head = bytes.copyOf(minOf(bytes.size, 64))
        // NUL 바이트가 있으면 바이너리 덤프로 간주한다.
        if (head.any { it == 0.toByte() }) return null
        val s = runCatching { bytes.toString(Charsets.UTF_8) }.getOrNull() ?: return null
        return s
    }
}
