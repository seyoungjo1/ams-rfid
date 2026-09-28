package com.ams.rfid.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import com.ams.rfid.R
import com.ams.rfid.core.BambuKeys
import com.ams.rfid.core.CloneResult
import com.ams.rfid.core.CuidCheck
import com.ams.rfid.core.DumpValidator
import com.ams.rfid.core.FilamentInfo
import com.ams.rfid.core.MifareCard
import com.ams.rfid.core.TagCloner
import com.ams.rfid.core.TagDump
import com.ams.rfid.data.FilamentEntry
import com.ams.rfid.data.FilamentLibrary
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.concurrent.thread

enum class Tab { LIBRARY, READ, HELP }

sealed interface LibraryState {
    data object Loading : LibraryState
    data class Ready(val library: FilamentLibrary) : LibraryState
    data class Error(val message: String) : LibraryState
}

/** 태그를 대면 실행할 대기 중인 작업. */
sealed interface Armed {
    data object None : Armed
    data class Write(val entry: FilamentEntry, val dump: TagDump) : Armed
    data object Read : Armed
    data object CuidCheck : Armed
}

/** 작업 진행/결과 상태. */
sealed interface OpStatus {
    data object Idle : OpStatus
    data class Progress(val message: String) : OpStatus
    data class Success(val message: String) : OpStatus
    data class Failure(val message: String) : OpStatus
    data class ReadDone(val info: FilamentInfo) : OpStatus
}

data class UiState(
    val tab: Tab = Tab.LIBRARY,
    val library: LibraryState = LibraryState.Loading,
    val query: String = "",
    val results: List<FilamentEntry> = emptyList(),
    val selected: FilamentEntry? = null,
    val armed: Armed = Armed.None,
    val status: OpStatus = OpStatus.Idle,
) {
    /** 태그를 대기하거나 결과를 보여주는 모달을 띄워야 하는지. */
    val showSheet: Boolean get() = armed != Armed.None || status != OpStatus.Idle
}

class MainViewModel(app: Application) : AndroidViewModel(app) {

    private val cloner = TagCloner()
    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    fun loadLibrary() {
        if (_ui.value.library is LibraryState.Ready) return
        thread(name = "library-load") {
            val state = try {
                val lib = FilamentLibrary.load(getApplication())
                LibraryState.Ready(lib)
            } catch (e: Exception) {
                LibraryState.Error(e.message ?: "라이브러리를 불러오지 못했습니다")
            }
            _ui.value = _ui.value.copy(
                library = state,
                results = (state as? LibraryState.Ready)?.library?.entries ?: emptyList(),
            )
        }
    }

    fun setTab(tab: Tab) {
        _ui.value = _ui.value.copy(tab = tab)
    }

    fun setQuery(query: String) {
        val lib = (_ui.value.library as? LibraryState.Ready)?.library
        val results = lib?.search(query) ?: emptyList()
        _ui.value = _ui.value.copy(query = query, results = results)
    }

    fun select(entry: FilamentEntry?) {
        _ui.value = _ui.value.copy(selected = entry)
    }

    fun armWrite(entry: FilamentEntry) {
        val sample = entry.samples.firstOrNull() ?: return
        val dump = try {
            sample.toDump()
        } catch (e: Exception) {
            _ui.value = _ui.value.copy(status = OpStatus.Failure(e.message ?: "덤프 오류"))
            return
        }
        _ui.value = _ui.value.copy(armed = Armed.Write(entry, dump), status = OpStatus.Idle)
    }

    fun armRead() {
        _ui.value = _ui.value.copy(armed = Armed.Read, status = OpStatus.Idle)
    }

    fun armCuidCheck() {
        _ui.value = _ui.value.copy(armed = Armed.CuidCheck, status = OpStatus.Idle)
    }

    fun dismissSheet() {
        _ui.value = _ui.value.copy(armed = Armed.None, status = OpStatus.Idle)
    }

    fun reportNotMifare() {
        if (_ui.value.armed == Armed.None) return
        _ui.value = _ui.value.copy(armed = Armed.None, status = OpStatus.Failure(str(R.string.nfc_not_mifare)))
    }

    /** NFC 콜백 스레드에서 호출된다. 대기 중인 작업을 카드에 대해 실행한다. */
    fun executeOnCard(card: MifareCard) {
        val armed = _ui.value.armed
        if (armed == Armed.None) return
        try {
            card.connect()
            when (armed) {
                is Armed.Write -> runWrite(card, armed.dump)
                Armed.Read -> runRead(card)
                Armed.CuidCheck -> runCuidCheck(card)
                Armed.None -> {}
            }
        } catch (e: Exception) {
            _ui.value = _ui.value.copy(status = OpStatus.Failure(e.message ?: "오류"))
        } finally {
            runCatching { card.close() }
            _ui.value = _ui.value.copy(armed = Armed.None)
        }
    }

    private fun runWrite(card: MifareCard, dump: TagDump) {
        progress(str(R.string.nfc_working, 0, 16))
        val result = cloner.clone(card, dump) { done, total ->
            progress(str(R.string.nfc_working, done, total))
        }
        when (result) {
            is CloneResult.Success -> {
                progress(str(R.string.nfc_verifying))
                when (val v = cloner.verify(card, dump)) {
                    is CloneResult.Success -> success(str(R.string.nfc_write_success))
                    is CloneResult.Failure -> failure(str(R.string.nfc_verify_failed, v.message))
                }
            }
            is CloneResult.Failure -> failure(str(R.string.nfc_write_failed, result.message))
        }
    }

    private fun runRead(card: MifareCard) {
        progress(str(R.string.nfc_reading))
        val keys = BambuKeys.derive(card.uid)
        val dump = cloner.readDump(card, keys)
        if (dump == null || !DumpValidator.validate(dump).ok) {
            failure(str(R.string.read_not_bambu))
            return
        }
        _ui.value = _ui.value.copy(status = OpStatus.ReadDone(FilamentInfo.parse(dump)))
    }

    private fun runCuidCheck(card: MifareCard) {
        progress(str(R.string.nfc_reading))
        when (cloner.checkCuid(card)) {
            CuidCheck.Writable -> success(str(R.string.cuid_writable))
            CuidCheck.NotWritable -> failure(str(R.string.cuid_not_writable))
            CuidCheck.NeedsFormat -> failure(str(R.string.cuid_needs_format))
            is CuidCheck.Error -> failure(str(R.string.nfc_read_failed, "카드 점검"))
        }
    }

    private fun progress(msg: String) {
        _ui.value = _ui.value.copy(status = OpStatus.Progress(msg))
    }

    private fun success(msg: String) {
        _ui.value = _ui.value.copy(status = OpStatus.Success(msg))
    }

    private fun failure(msg: String) {
        _ui.value = _ui.value.copy(status = OpStatus.Failure(msg))
    }

    private fun str(resId: Int, vararg args: Any): String =
        getApplication<Application>().getString(resId, *args)
}
