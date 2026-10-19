-- EDI.app: enciende EDI y muestra una ventana con el progreso real.
-- __EDI_DIR__ se reemplaza al compilar (scripts/03_crear_acceso_directo.sh).
on fmtTime(secs)
	if secs < 0 then return "calculando tiempo…"
	if secs < 3 then return "casi listo"
	if secs < 60 then return "≈ " & secs & " s restantes"
	set m to secs div 60
	set s to secs mod 60
	return "≈ " & m & " min " & s & " s restantes"
end fmtTime

on run
	set ediDir to "__EDI_DIR__"
	set statusFile to ediDir & "/data/launch-status"
	set logFile to ediDir & "/data/edi-launcher.log"
	do shell script "mkdir -p " & quoted form of (ediDir & "/data") & "; printf '0|Iniciando EDI|-1\\n' > " & quoted form of statusFile
	do shell script "/bin/bash " & quoted form of (ediDir & "/scripts/edi.sh") & " start >> " & quoted form of logFile & " 2>&1 &"

	set progress total steps to 100
	set progress completed steps to 0
	set progress description to "Encendiendo EDI"
	set progress additional description to "Iniciando…"
	set lastLine to ""
	set stuck to 0
	try
		repeat
			delay 0.5
			set statusLine to do shell script "cat " & quoted form of statusFile & " 2>/dev/null || echo '0|Iniciando EDI|-1'"
			if statusLine is lastLine then
				set stuck to stuck + 1
			else
				set stuck to 0
				set lastLine to statusLine
			end if
			set AppleScript's text item delimiters to "|"
			set parts to text items of statusLine
			set AppleScript's text item delimiters to ""
			if (count of parts) < 3 then set parts to {"0", "Iniciando EDI", "-1"}
			set pct to (item 1 of parts) as integer
			set msg to item 2 of parts
			set eta to (item 3 of parts) as integer

			if pct < 0 then
				set progress additional description to "Error"
				set r to display dialog "No se pudo encender EDI." & return & return & msg buttons {"Ver registro", "Cerrar"} default button "Cerrar" with title "EDI" with icon caution
				if button returned of r is "Ver registro" then do shell script "open -e " & quoted form of logFile
				return
			end if

			set progress completed steps to pct
			set progress description to "Encendiendo EDI · " & pct & "%"
			set progress additional description to msg & "  —  " & my fmtTime(eta)
			if pct ≥ 100 then
				delay 0.8
				exit repeat
			end if
			-- 6 minutos sin ningún cambio: avisa en lugar de quedarse colgado
			if stuck > 720 then
				set r to display dialog "EDI lleva mucho tiempo en: " & msg & return & "¿Quieres ver el registro?" buttons {"Ver registro", "Seguir esperando"} default button "Seguir esperando" with title "EDI"
				if button returned of r is "Ver registro" then do shell script "open -e " & quoted form of logFile
				set stuck to 0
			end if
		end repeat
	on error number -128
		-- el usuario pulsó Detener: EDI sigue encendiéndose en segundo plano
	end try
end run
