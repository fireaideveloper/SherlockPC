"""Entry point shared by source and the Windows frozen executable."""
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    from sherlock.collector_gui import main
    main()
