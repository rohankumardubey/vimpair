if has("python3")
  let s:VimpairPythonCommand="python3"
elseif has("python")
  let s:VimpairPythonCommand="python"
else
  echo "Vimpair needs to be run with python- or python3 support enabled!"
  finish
endif

function! g:VimpairRunPython(command)
  execute(s:VimpairPythonCommand . " " . a:command)
endfunction

call g:VimpairRunPython("import sys, os, vim")
call g:VimpairRunPython(
      \  "sys.path.append(os.path.abspath(os.path.join('" .
      \  expand("<sfile>:p:h") . "', '..', 'python', 'vimpair')))"
      \)

call g:VimpairRunPython(
      \  "import vimpair                                                    \n" .
      \  "from connection import create_client_socket, create_server_socket \n" .
      \  "from connectors import ClientConnector, ServerConnector           \n" .
      \  "from protocol import MessageHandler                               \n" .
      \  "from session import Session"
      \)

call g:VimpairRunPython(
      \  "server_socket_factory = create_server_socket \n" .
      \  "client_socket_factory = create_client_socket \n" .
      \  "session = None                               \n" .
      \  "message_handler = None"
      \)


let g:VimpairConcealFilePaths = 1
let g:VimpairShowStatusMessages = 1
let g:VimpairTimerInterval = 200


function! s:VimpairStartObserving()
  augroup VimpairEditorObservers
    autocmd TextChanged * call g:VimpairRunPython("vimpair.send_contents_update()")
    autocmd TextChangedI * call g:VimpairRunPython("vimpair.send_contents_update()")
    autocmd InsertLeave * call g:VimpairRunPython("vimpair.update_contents_and_cursor()")
    autocmd CursorMoved * call g:VimpairRunPython("vimpair.send_cursor_position()")
    autocmd CursorMovedI * call g:VimpairRunPython("vimpair.send_cursor_position()")
    autocmd BufEnter * call g:VimpairRunPython("vimpair.send_file_change()")
    autocmd BufWritePost * call g:VimpairRunPython(
          \ "vimpair.send_file_change(); vimpair.send_save_file()")
  augroup END
endfunction

function! s:VimpairStopObserving()
  augroup VimpairEditorObservers
    autocmd!
  augroup END
endfunction


let s:VimpairTimer = ""

function! s:VimpairStartTimer(timer_command)
  let s:VimpairTimer = timer_start(
        \  g:VimpairTimerInterval,
        \  {-> execute(a:timer_command, "")},
        \  {'repeat': -1}
        \)
endfunction

function! s:VimpairStopTimer()
  if s:VimpairTimer != ""
    call timer_stop(s:VimpairTimer)
    let s:VimpairTimer = ""
  endif
endfunction


function! s:VimpairStartReceivingMessagesTimer()
  call s:VimpairStartTimer(
        \  "call g:VimpairRunPython(\"message_handler.process(" .
        \  "    vimpair.connector.connection.received_messages" .
        \  ")\")"
        \)
endfunction

function! s:VimpairTakeControl()
  call s:VimpairStopTimer()
  call s:VimpairStartObserving()
endfunction

function! s:VimpairReleaseControl()
  call s:VimpairStopObserving()
  call s:VimpairStartReceivingMessagesTimer()
endfunction


function! s:VimpairInitialize()
  augroup VimpairCleanup
    autocmd VimLeavePre * call s:VimpairCleanup()
  augroup END

  call g:VimpairRunPython(
        \  "message_handler = MessageHandler(" .
        \  "    callbacks=vimpair.VimCallbacks(" .
        \  "        take_control=lambda: vim.command('call s:VimpairTakeControl()')," .
        \  "        session=session," .
        \  "    )" .
        \  ")"
        \)
endfunction

function! s:VimpairCleanup()
  call s:VimpairStopTimer()
  call s:VimpairStopObserving()

  augroup VimpairCleanup
    autocmd!
  augroup END

  call g:VimpairRunPython("message_handler = None")
  call g:VimpairRunPython("vimpair.connector.disconnect()")
endfunction


function! VimpairServerStart()
  call s:VimpairInitialize()

  call g:VimpairRunPython("vimpair.connector = ClientConnector(server_socket_factory)")

  call s:VimpairStartTimer(
        \  "call g:VimpairRunPython(\"" .
        \  "if vimpair.check_for_new_client(): vim.command('call s:VimpairStopTimer()')" .
        \  "\")"
        \)
  call s:VimpairStartObserving()
  call g:VimpairRunPython(
        \  "vimpair.send_file_change.enabled = True \n" .
        \  "vimpair.send_file_change.should_conceal_path =" .
        \  "    lambda: int(vim.eval('g:VimpairConcealFilePaths')) != 0 \n" .
        \  "vimpair.send_file_change()"
        \)
endfunction

function! VimpairServerStop()
  call s:VimpairCleanup()
endfunction


function! VimpairClientStart()
  call g:VimpairRunPython("session = Session()")
  call s:VimpairInitialize()

  call g:VimpairRunPython("vimpair.connector = ServerConnector(client_socket_factory)")

  call g:VimpairRunPython("vimpair.send_file_change.enabled = False")
  call s:VimpairStartReceivingMessagesTimer()
endfunction

function! VimpairClientStop()
  call s:VimpairCleanup()
  call g:VimpairRunPython("session.end()")
  call g:VimpairRunPython("session = None")
endfunction


function! VimpairHandover()
  call g:VimpairRunPython(
        \  "if vimpair.hand_over_control():" .
        \  "    vim.command('call s:VimpairReleaseControl()')"
        \)
endfunction


command! -nargs=0 VimpairServerStart :call VimpairServerStart()
command! -nargs=0 VimpairServerStop :call VimpairServerStop()
command! -nargs=0 VimpairClientStart :call VimpairClientStart()
command! -nargs=0 VimpairClientStop :call VimpairClientStop()
command! -nargs=0 VimpairHandover :call VimpairHandover()
