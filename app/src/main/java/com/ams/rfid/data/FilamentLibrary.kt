package com.ams.rfid.data

import android.content.Context
import android.util.Base64
import com.ams.rfid.core.TagDump
import org.json.JSONObject

/** 라이브러리에 담긴 하나의 태그 샘플(원본 UID + base64 덤프). */
data class TagSample(val uid: String, private val dumpB64: String) {
    fun toDump(): TagDump = TagDump.of(Base64.decode(dumpB64, Base64.DEFAULT))
}

/** 목록/스와치 표시용 요약 정보(첫 샘플에서 추출, 빌드 시 미리 계산됨). */
data class EntryInfo(
    val colorHex: String,
    val color2Hex: String?,
    val type: String,
    val detailType: String,
    val weightGram: Int,
    val diameterMm: Double,
    val minHotendC: Int,
    val maxHotendC: Int,
    val bedTempC: Int,
) {
    /** '#RRGGBBAA' 또는 '#RRGGBB' 에서 6자리 RGB 만 취해 '#RRGGBB' 로 반환. */
    fun rgb(hex: String): String {
        val h = hex.removePrefix("#")
        return "#" + (if (h.length >= 6) h.substring(0, 6) else h.padEnd(6, '0'))
    }
}

/** 재질/색상 단위의 라이브러리 항목. */
data class FilamentEntry(
    val category: String,
    val material: String,
    val color: String,
    val info: EntryInfo?,
    val samples: List<TagSample>,
) {
    val displayName: String get() = "$material · $color"
    val searchKey: String = "$category $material $color".lowercase()
}

data class FilamentLibrary(
    val commit: String,
    val entries: List<FilamentEntry>,
) {
    fun search(query: String): List<FilamentEntry> {
        val q = query.trim().lowercase()
        if (q.isEmpty()) return entries
        val tokens = q.split(Regex("\\s+"))
        return entries.filter { entry -> tokens.all { entry.searchKey.contains(it) } }
    }

    companion object {
        /** assets/library/index.json 을 읽어 파싱한다. */
        fun load(context: Context): FilamentLibrary {
            val text = context.assets.open("library/index.json").bufferedReader().use { it.readText() }
            val root = JSONObject(text)
            val commit = root.optString("commit", "")
            val arr = root.getJSONArray("entries")
            val entries = ArrayList<FilamentEntry>(arr.length())
            for (i in 0 until arr.length()) {
                val e = arr.getJSONObject(i)
                val samplesArr = e.getJSONArray("samples")
                val samples = ArrayList<TagSample>(samplesArr.length())
                for (j in 0 until samplesArr.length()) {
                    val s = samplesArr.getJSONObject(j)
                    samples.add(TagSample(s.getString("uid"), s.getString("dump")))
                }
                val info = e.optJSONObject("info")?.let { io ->
                    EntryInfo(
                        colorHex = io.optString("colorHex", "#808080"),
                        color2Hex = if (io.isNull("color2")) null else io.optString("color2", null),
                        type = io.optString("type", ""),
                        detailType = io.optString("detailType", ""),
                        weightGram = io.optInt("weight", 0),
                        diameterMm = io.optDouble("diameter", 1.75),
                        minHotendC = io.optInt("tmin", 0),
                        maxHotendC = io.optInt("tmax", 0),
                        bedTempC = io.optInt("bed", 0),
                    )
                }
                entries.add(
                    FilamentEntry(
                        category = e.getString("category"),
                        material = e.getString("material"),
                        color = e.getString("color"),
                        info = info,
                        samples = samples,
                    ),
                )
            }
            return FilamentLibrary(commit, entries)
        }
    }
}
