; z80: assembler=fantams buildmode=sna base=cpc6128-en
; ============================================================================
; Test de synchro PSG (sortie interne) / Digiblaster (greffon)
;
; Toutes les 50 trames (1 s), un "clic" de 40 ms demarre au meme instant :
;   - sur le PSG   : tone ~1 kHz, voie A
;   - sur la Digiblaster (port &EFxx) : carre ~1 kHz
; Le border passe en blanc pendant le clic.
;
; A l'oreille : un seul clic net = synchro correcte. Un "flam" (double
; attaque) ou un retard qui grandit/diminue au fil du temps = le greffon
; derive. Dans le mixeur systeme, couper tour a tour une des deux entrees
; de lite pour entendre chaque source seule.
;
; Assembler : fantams sync_test.asm -o sync_test.sna
; ============================================================================

FRAMES  equ 50          ; trames entre deux clics
HALFPER equ 118         ; demi-periode du carre Digiblaster (~500 us)
NTOGGLE equ 80          ; 80 demi-periodes = 40 ms
LVL_LO     equ #20
LVL_HI    equ #E0

        org #4000
        run start

start:  di
        ld sp,#bff0

        ld bc,#f782             ; PPI : port A sortie, B entree, C sortie
        ld a,#82
        out (c),a
        ld bc,#f600             ; PSG inactif
        out (c),c

        ld c,7                  ; mixer : tone A seul
        ld a,#3e
        call psg_write
        ld c,0                  ; periode tone A = 62 (~1 kHz)
        ld a,62
        call psg_write
        ld c,1
        xor a
        call psg_write
        ld c,8                  ; volume A = 0
        xor a
        call psg_write

        ld bc,#7f10             ; border bleu
        ld a,#44
        out (c),c
        out (c),a

        ld bc,#efff             ; Digiblaster au repos
        ld a,#80
        out (c),a

main:   ld d,FRAMES
frame:  call wait_vsync
        dec d
        jr nz,frame

        ; ---- clic : PSG puis Digiblaster, a quelques dizaines de us d'ecart
        ld c,8                  ; volume A = 15
        ld a,15
        call psg_write
        ld bc,#7f10             ; border blanc
        ld a,#4b
        out (c),c
        out (c),a

        ld bc,#ef00
        ld e,NTOGGLE
        ld a,LVL_LO
tog:    out (c),a               ; 4
        xor LVL_LO ^ LVL_HI          ; 2 : alterne LVL_LO / LVL_HI
        ld h,HALFPER            ; 2
dly:    dec h                   ; 1
        jr nz,dly               ; 3 (2 au dernier tour)
        dec e                   ; 1
        jr nz,tog               ; 3

        ld bc,#efff             ; Digiblaster au repos
        ld a,#80
        out (c),a
        ld c,8                  ; volume A = 0
        xor a
        call psg_write
        ld bc,#7f10             ; border bleu
        ld a,#44
        out (c),c
        out (c),a
        jr main

; Attend un front montant de VSYNC (PPI port B bit 0)
wait_vsync:
        ld b,#f5
wv0:    in a,(c)
        rra
        jr c,wv0                ; sort d'un eventuel VSYNC en cours
wv1:    in a,(c)
        rra
        jr nc,wv1
        ret

; Ecrit A dans le registre PSG C
psg_write:
        ld b,#f4
        out (c),c
        ld bc,#f6c0
        out (c),c
        ld bc,#f600
        out (c),c
        ld b,#f4
        out (c),a
        ld bc,#f680
        out (c),c
        ld bc,#f600
        out (c),c
        ret
